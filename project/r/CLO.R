# (c) 2027, Michael Robbins
library(grDevices)

`%||%` <- function(x, y) if (is.null(x) || length(x) == 0 || is.na(x)) y else x

script_arg <- commandArgs(trailingOnly = FALSE)
script_file <- sub("^--file=", "", script_arg[grep("^--file=", script_arg)][1] %||% NA_character_)
script_dir <- dirname(normalizePath(script_file %||% "CLO.R", winslash = "/", mustWork = FALSE))

set.seed(42)
num_paths <- 25000
horizon_years <- 5
discount_rate <- 0.04
output_root <- file.path(script_dir, "rendered-sample")
dir.create(output_root, recursive = TRUE, showWarnings = FALSE)

tranches <- data.frame(
  tranche = c("Equity", "Mezzanine", "Senior"),
  attach = c(0.00, 0.06, 0.14),
  detach = c(0.06, 0.14, 0.30),
  trigger_level = c(0.03, 0.10, 0.18),
  stringsAsFactors = FALSE
)
tranches$width <- tranches$detach - tranches$attach

save_dual_plot <- function(path, plot_fn, width = 8.2, height = 5.2) {
  png(path, width = width, height = height, units = "in", res = 220)
  plot_fn()
  dev.off()
  svg(sub("\\.png$", ".svg", path), width = width, height = height)
  plot_fn()
  dev.off()
}

tranche_loss_on_par <- function(loss_fraction, attach, detach) {
  pmin(pmax(loss_fraction - attach, 0), detach - attach)
}

tranche_loss_on_notional <- function(loss_fraction, attach, detach) {
  tranche_loss_on_par(loss_fraction, attach, detach) / (detach - attach)
}

joint_default_probability <- function(p, rho) {
  threshold <- qnorm(p)
  integrand <- function(z) dnorm(z) * pnorm((threshold - sqrt(rho) * z) / sqrt(1 - rho))^2
  integrate(integrand, lower = -8, upper = 8L)$value
}

build_observed_cohort_panel <- function() {
  sectors <- c("Software", "Retail", "Healthcare", "Energy", "Telecom", "Services", "Industrials", "Transport")
  base_pd <- c(0.010, 0.016, 0.012, 0.022, 0.018, 0.015, 0.020, 0.017)
  years <- 2013:2024
  true_rho <- 0.16
  year_factor <- rnorm(length(years))
  rows <- vector("list", length(years) * length(sectors))
  idx <- 1
  for (y in seq_along(years)) {
    for (s in seq_along(sectors)) {
      cohort_size <- sample(110:220, 1)
      sector_tilt <- 0.002 * sin(0.7 * s + 0.4 * y)
      pd_1y <- min(max(base_pd[s] + sector_tilt, 0.006), 0.045)
      conditional_pd <- pnorm((qnorm(pd_1y) - sqrt(true_rho) * year_factor[y]) / sqrt(1 - true_rho))
      defaults <- rbinom(1, cohort_size, conditional_pd)
      rows[[idx]] <- data.frame(
        year = years[y],
        sector = sectors[s],
        cohort_size = cohort_size,
        annual_pd = pd_1y,
        defaults = defaults,
        default_rate = defaults / cohort_size
      )
      idx <- idx + 1
    }
  }
  do.call(rbind, rows)
}

calibrate_asset_correlation <- function(panel) {
  pooled_pd <- sum(panel$defaults) / sum(panel$cohort_size)
  observed_var <- var(panel$default_rate)
  mean_cohort_size <- mean(panel$cohort_size)
  rho_grid <- seq(0.01, 0.35, length.out = 70)
  model_var <- numeric(length(rho_grid))
  objective <- numeric(length(rho_grid))
  for (i in seq_along(rho_grid)) {
    rho <- rho_grid[i]
    pair_default <- joint_default_probability(pooled_pd, rho)
    conditional_var <- pooled_pd * (1 - pooled_pd) / mean_cohort_size
    common_factor_var <- (1 - 1 / mean_cohort_size) * (pair_default - pooled_pd^2)
    model_var[i] <- conditional_var + common_factor_var
    objective[i] <- (observed_var - model_var[i])^2
  }
  calibration <- data.frame(
    rho = rho_grid,
    pooled_pd = pooled_pd,
    observed_default_rate_var = observed_var,
    model_default_rate_var = model_var,
    objective = objective
  )
  rho_hat <- calibration$rho[which.min(calibration$objective)]
  list(rho_hat = rho_hat, calibration = calibration)
}

simulate_model_implied_cohort_rates <- function(cohort_sizes, pooled_pd, rho) {
  systemic <- rnorm(length(cohort_sizes))
  conditional_pd <- pnorm((qnorm(pooled_pd) - sqrt(rho) * systemic) / sqrt(1 - rho))
  defaults <- rbinom(length(cohort_sizes), cohort_sizes, conditional_pd)
  defaults / cohort_sizes
}

build_loan_pool <- function() {
  num_loans <- 400
  exposures <- rlnorm(num_loans, meanlog = 0.0, sdlog = 0.45)
  weights <- exposures / sum(exposures)
  annual_pd <- pmin(pmax(rbeta(num_loans, 2.2, 14.0) * 0.12, 0.010), 0.060)
  annual_cpr <- pmin(pmax(rbeta(num_loans, 2.5, 9.0) * 0.18, 0.020), 0.100)
  lgd <- pmin(pmax(0.30 + 0.45 * rbeta(num_loans, 3.0, 3.0), 0.30), 0.70)
  sectors <- c("Software", "Retail", "Healthcare", "Energy", "Telecom", "Industrials")
  data.frame(
    loan_id = sprintf("L%03d", seq_len(num_loans)),
    weight = weights,
    annual_pd = annual_pd,
    annual_cpr = annual_cpr,
    lgd = lgd,
    sector = sample(sectors, num_loans, replace = TRUE),
    stringsAsFactors = FALSE
  )
}

run_tranche_engine <- function(pool, tranches, rho, num_paths, horizon_years, discount_rate) {
  num_loans <- nrow(pool)
  num_tranches <- nrow(tranches)
  active <- matrix(TRUE, nrow = num_loans, ncol = num_paths)
  outstanding <- matrix(rep(tranches$width, num_paths), nrow = num_tranches, byrow = FALSE)
  cumulative_loss <- rep(0, num_paths)
  prior_tranche_loss_par <- matrix(0, nrow = num_tranches, ncol = num_paths)
  premium_leg <- matrix(0, nrow = num_tranches, ncol = num_paths)
  protection_leg <- matrix(0, nrow = num_tranches, ncol = num_paths)
  trigger_any <- matrix(FALSE, nrow = num_tranches, ncol = num_paths)
  collateral_loss_path <- matrix(0, nrow = horizon_years, ncol = num_paths)
  active_collateral_path <- matrix(0, nrow = horizon_years, ncol = num_paths)

  for (year in seq_len(horizon_years)) {
    discount <- exp(-discount_rate * year)
    premium_leg <- premium_leg + discount * (outstanding / tranches$width)

    systemic <- rnorm(num_paths)
    idiosyncratic <- matrix(rnorm(num_loans * num_paths), nrow = num_loans, ncol = num_paths)
    latent_asset <- sqrt(rho) * matrix(rep(systemic, each = num_loans), nrow = num_loans) +
      sqrt(1 - rho) * idiosyncratic
    default_event <- active & (latent_asset < qnorm(pool$annual_pd))
    prepay_draw <- matrix(runif(num_loans * num_paths), nrow = num_loans, ncol = num_paths)
    prepay_event <- active & (!default_event) & (prepay_draw < pool$annual_cpr)

    default_loss <- colSums((pool$weight * pool$lgd) * default_event)
    recovery_cash <- colSums((pool$weight * (1 - pool$lgd)) * default_event)
    prepaid_principal <- colSums(pool$weight * prepay_event)

    active <- active & (!default_event) & (!prepay_event)
    active_collateral <- colSums(pool$weight * active)
    cumulative_loss <- cumulative_loss + default_loss
    collateral_loss_path[year, ] <- cumulative_loss
    active_collateral_path[year, ] <- active_collateral

    tranche_loss_par <- vapply(
      seq_len(num_tranches),
      function(i) tranche_loss_on_par(cumulative_loss, tranches$attach[i], tranches$detach[i]),
      numeric(num_paths)
    )
    tranche_loss_par <- t(tranche_loss_par)
    incremental_tranche_loss <- tranche_loss_par - prior_tranche_loss_par
    prior_tranche_loss_par <- tranche_loss_par

    protection_leg <- protection_leg + discount * (incremental_tranche_loss / tranches$width)
    outstanding <- pmax(outstanding - incremental_tranche_loss, 0)

    collections <- recovery_cash + prepaid_principal
    for (tranche_idx in c(3, 2, 1)) {
      allocation <- pmin(outstanding[tranche_idx, ], collections)
      outstanding[tranche_idx, ] <- outstanding[tranche_idx, ] - allocation
      collections <- collections - allocation
    }

    year_trigger <- outer(tranches$trigger_level, cumulative_loss, function(threshold, loss) loss >= threshold)
    trigger_any <- trigger_any | year_trigger
  }

  final_tranche_loss_par <- prior_tranche_loss_par
  final_tranche_loss_notional <- final_tranche_loss_par / tranches$width
  fair_spread_bps <- 1e4 * rowMeans(protection_leg) / rowMeans(premium_leg)

  list(
    collateral_loss_path = collateral_loss_path,
    active_collateral_path = active_collateral_path,
    trigger_any = trigger_any,
    final_tranche_loss_par = final_tranche_loss_par,
    final_tranche_loss_notional = final_tranche_loss_notional,
    fair_spread_bps = fair_spread_bps
  )
}

summarize_tranches <- function(results, tranches, label) {
  rows <- lapply(seq_len(nrow(tranches)), function(i) {
    loss_series <- results$final_tranche_loss_notional[i, ]
    q99 <- as.numeric(quantile(loss_series, 0.99, names = FALSE))
    data.frame(
      scenario = label,
      tranche = tranches$tranche[i],
      expected_loss_pct = 100 * mean(loss_series),
      var99_pct = 100 * q99,
      cvar99_pct = 100 * mean(loss_series[loss_series >= q99]),
      trigger_frequency_pct = 100 * mean(results$trigger_any[i, ]),
      loss_compensation_spread_bps = results$fair_spread_bps[i]
    )
  })
  do.call(rbind, rows)
}

plot_cdf_pair <- function(low_series, high_series, xlab_text, title_text, path) {
  save_dual_plot(path, function() {
    low_sorted <- sort(low_series)
    high_sorted <- sort(high_series)
    prob <- ((seq_along(low_sorted) - 0.5) / length(low_sorted))
    plot(100 * low_sorted, prob, type = "s", lwd = 2, col = "#2A7F62",
         xlab = xlab_text, ylab = "CDF", main = title_text)
    lines(100 * high_sorted, prob, type = "s", lwd = 2, col = "#B63A2B")
    grid(col = "grey85")
    legend("bottomright", legend = c("Low rho", "High rho"), lwd = 2, col = c("#2A7F62", "#B63A2B"), bty = "n")
  })
}

cohort_panel <- build_observed_cohort_panel()
calibration_obj <- calibrate_asset_correlation(cohort_panel)
rho_hat <- calibration_obj$rho_hat
calibration_grid <- calibration_obj$calibration
pooled_pd <- calibration_grid$pooled_pd[1]
model_implied_rates <- simulate_model_implied_cohort_rates(cohort_panel$cohort_size, pooled_pd, rho_hat)

loan_pool <- build_loan_pool()
rho_low <- max(0.5 * rho_hat, 0.03)
rho_high <- min(2.5 * rho_hat, 0.45)

results_low <- run_tranche_engine(loan_pool, tranches, rho_low, num_paths, horizon_years, discount_rate)
results_high <- run_tranche_engine(loan_pool, tranches, rho_high, num_paths, horizon_years, discount_rate)

summary_low <- summarize_tranches(results_low, tranches, "low")
summary_high <- summarize_tranches(results_high, tranches, "high")
summary_table <- rbind(summary_low, summary_high)
scenario_table <- data.frame(
  scenario = c("base", "low", "high"),
  rho = c(rho_hat, rho_low, rho_high),
  pooled_cohort_pd = c(pooled_pd, pooled_pd, pooled_pd)
)

write.csv(cohort_panel, file.path(output_root, "clo-observed-cohort-panel.csv"), row.names = FALSE)
write.csv(calibration_grid, file.path(output_root, "clo-rho-calibration-grid.csv"), row.names = FALSE)
write.csv(summary_table, file.path(output_root, "clo-tranche-summary-metrics.csv"), row.names = FALSE)
write.csv(scenario_table, file.path(output_root, "clo-rho-scenarios.csv"), row.names = FALSE)

loss_grid <- seq(0, 0.50, length.out = 500)
save_dual_plot(file.path(output_root, "clo-payoff-map.png"), function() {
  plot(100 * loss_grid, 100 * tranche_loss_on_notional(loss_grid, tranches$attach[1], tranches$detach[1]),
       type = "l", lwd = 2.2, col = "#2A7F62", xlab = "Collateral par loss fraction (%)",
       ylab = "Tranche principal loss / tranche notional (%)",
       main = "Payoff map: the waterfall turns one pool loss into three kinked tranche losses")
  lines(100 * loss_grid, 100 * tranche_loss_on_notional(loss_grid, tranches$attach[2], tranches$detach[2]), lwd = 2.2, col = "#2451B7")
  lines(100 * loss_grid, 100 * tranche_loss_on_notional(loss_grid, tranches$attach[3], tranches$detach[3]), lwd = 2.2, col = "#B63A2B")
  grid(col = "grey85")
  legend("topleft", legend = c("Equity [0,6%]", "Mezzanine [6,14%]", "Senior [14,30%]"),
         lwd = 2.2, col = c("#2A7F62", "#2451B7", "#B63A2B"), bty = "n")
})

save_dual_plot(file.path(output_root, "clo-rho-calibration-objective.png"), function() {
  plot(calibration_grid$rho, calibration_grid$objective, type = "l", lwd = 2.2, col = "#2451B7",
       xlab = "Asset correlation rho", ylab = "Squared variance-fit error",
       main = "Dependence calibration from repeated cohort default-rate dispersion")
  abline(v = rho_hat, lty = 2, lwd = 1.5)
  grid(col = "grey85")
})

save_dual_plot(file.path(output_root, "clo-rho-calibration-fit.png"), function() {
  obs_sorted <- sort(cohort_panel$default_rate)
  mdl_sorted <- sort(model_implied_rates)
  obs_prob <- ((seq_along(obs_sorted) - 0.5) / length(obs_sorted))
  plot(100 * obs_sorted, obs_prob, type = "s", lwd = 2, col = "black",
       xlab = "Annual cohort default rate (%)", ylab = "Empirical CDF",
       main = "Observed cohort dispersion versus the fitted Vasicek dispersion")
  lines(100 * mdl_sorted, obs_prob, type = "s", lwd = 2, col = "#2451B7")
  grid(col = "grey85")
  legend("bottomright",
         legend = c("Observed cohort panel", sprintf("Fitted Vasicek panel (p=%0.2f%%, rho=%0.3f)", 100 * pooled_pd, rho_hat)),
         lwd = 2, col = c("black", "#2451B7"), bty = "n")
})

plot_cdf_pair(results_low$collateral_loss_path[horizon_years, ], results_high$collateral_loss_path[horizon_years, ],
              "Five-year collateral par loss (%)",
              "Same marginals, different dependence: rho mainly changes the tail",
              file.path(output_root, "clo-collateral-loss-cdf-low-vs-high.png"))

plot_cdf_pair(results_low$final_tranche_loss_notional[1, ], results_high$final_tranche_loss_notional[1, ],
              "Equity principal loss / tranche notional (%)",
              "Equity tranche loss distribution",
              file.path(output_root, "clo-equity-loss-cdf-low-vs-high.png"))

plot_cdf_pair(results_low$final_tranche_loss_notional[2, ], results_high$final_tranche_loss_notional[2, ],
              "Mezzanine principal loss / tranche notional (%)",
              "Mezzanine tranche loss distribution",
              file.path(output_root, "clo-mezzanine-loss-cdf-low-vs-high.png"))

plot_cdf_pair(results_low$final_tranche_loss_notional[3, ], results_high$final_tranche_loss_notional[3, ],
              "Senior principal loss / tranche notional (%)",
              "Senior tranche loss distribution",
              file.path(output_root, "clo-senior-loss-cdf-low-vs-high.png"))

save_dual_plot(file.path(output_root, "clo-tranche-tail-metrics-low-vs-high.png"), function() {
  bar_centers <- barplot(rbind(summary_low$expected_loss_pct, summary_low$var99_pct, summary_low$cvar99_pct,
                               summary_high$expected_loss_pct, summary_high$var99_pct, summary_high$cvar99_pct),
                         beside = TRUE, col = c("#7FBF9A", "#4E9CFF", "#2F5DB5", "#E9938A", "#D96657", "#B63A2B"),
                         names.arg = tranches$tranche, ylab = "Loss metric (% of tranche notional)",
                         main = "Tail metrics move sharply once dependence pushes mass through the tranche kink")
  grid(col = "grey85")
  legend("topleft",
         legend = c("Low rho: Expected loss", "Low rho: VaR 99%", "Low rho: CVaR 99%",
                    "High rho: Expected loss", "High rho: VaR 99%", "High rho: CVaR 99%"),
         fill = c("#7FBF9A", "#4E9CFF", "#2F5DB5", "#E9938A", "#D96657", "#B63A2B"), bty = "n")
})

save_dual_plot(file.path(output_root, "clo-trigger-frequencies-low-vs-high.png"), function() {
  barplot(rbind(summary_low$trigger_frequency_pct, summary_high$trigger_frequency_pct),
          beside = TRUE, col = c("#2A7F62", "#B63A2B"), names.arg = tranches$tranche,
          ylab = "Pathwise trigger breach frequency (%)", main = "Trigger frequencies by tranche")
  grid(col = "grey85")
  legend("topleft", legend = c("Low rho", "High rho"), fill = c("#2A7F62", "#B63A2B"), bty = "n")
})

save_dual_plot(file.path(output_root, "clo-loss-compensation-spread-low-vs-high.png"), function() {
  barplot(rbind(summary_low$loss_compensation_spread_bps, summary_high$loss_compensation_spread_bps),
          beside = TRUE, col = c("#2A7F62", "#B63A2B"), names.arg = tranches$tranche,
          ylab = "Break-even loss-compensation spread (bps)", main = "Loss-compensation spread by tranche")
  grid(col = "grey85")
  legend("topleft", legend = c("Low rho", "High rho"), fill = c("#2A7F62", "#B63A2B"), bty = "n")
})

cat("\nCalibrated rho settings\n")
print(scenario_table)
cat("\nTranche summary metrics\n")
print(summary_table)

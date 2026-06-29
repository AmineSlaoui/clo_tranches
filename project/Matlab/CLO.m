% (c) 2027, Michael Robbins
%% Collateralized Loan Obligation
% This MATLAB notebook mirrors the public Python CLO example.
% It calibrates rho from repeated cohort default-rate dispersion, then runs
% a same-marginals low-rho versus high-rho experiment with true tranche
% loss distributions, pathwise warning triggers, and loss-compensation spreads.

%% Configuration
% Keep the public example reproducible and small enough to inspect.
rng(42, "twister");
numPaths = 25000;
horizonYears = 5;
discountRate = 0.04;
outputRoot = fullfile(fileparts(mfilename("fullpath")), "rendered-sample");
if ~exist(outputRoot, "dir")
    mkdir(outputRoot);
end

%% Public Tranche Inputs
% The tranche structure is the only structural input readers need.
trancheNames = ["Equity"; "Mezzanine"; "Senior"];
attach = [0.00; 0.06; 0.14];
detach = [0.06; 0.14; 0.30];
triggerLevel = [0.03; 0.10; 0.18];
width = detach - attach;

%% Build an Observed Cohort Panel
% Repeated cohort default-rate dispersion gives a minimal empirical anchor for rho.
cohortPanel = buildObservedCohortPanel();
[rhoHat, calibrationGrid] = calibrateAssetCorrelation(cohortPanel);
pooledPd = calibrationGrid.pooled_pd(1);
modelImpliedRates = simulateModelImpliedCohortRates(cohortPanel.cohort_size, pooledPd, rhoHat);

%% Build the Loan Pool and Dependence Scenarios
% Hold marginals fixed so only dependence changes between the two scenarios.
loanPool = buildLoanPool();
rhoLow = max(0.5 * rhoHat, 0.03);
rhoHigh = min(2.5 * rhoHat, 0.45);

resultsLow = runTrancheEngine(loanPool, attach, detach, triggerLevel, width, rhoLow, numPaths, horizonYears, discountRate);
resultsHigh = runTrancheEngine(loanPool, attach, detach, triggerLevel, width, rhoHigh, numPaths, horizonYears, discountRate);

summaryLow = summarizeTranches(resultsLow, trancheNames, "low");
summaryHigh = summarizeTranches(resultsHigh, trancheNames, "high");
summaryTable = [summaryLow; summaryHigh];

scenarioTable = table( ...
    ["base"; "low"; "high"], ...
    [rhoHat; rhoLow; rhoHigh], ...
    [pooledPd; pooledPd; pooledPd], ...
    'VariableNames', {'scenario', 'rho', 'pooled_cohort_pd'});

%% Save the Tables Used by the Chapter
% Persist the compact tables so the prose and figures can quote exact values.
writetable(cohortPanel, fullfile(outputRoot, "clo-observed-cohort-panel.csv"));
writetable(calibrationGrid, fullfile(outputRoot, "clo-rho-calibration-grid.csv"));
writetable(scenarioTable, fullfile(outputRoot, "clo-rho-scenarios.csv"));
writetable(summaryTable, fullfile(outputRoot, "clo-tranche-summary-metrics.csv"));

%% Figure 1: Payoff Map
% The waterfall is a deterministic kinked mapping from collateral loss to tranche loss.
lossGrid = linspace(0.0, 0.50, 500)';
fig = figure("Color", "white", "Position", [100 100 880 520]);
hold on;
for i = 1:numel(trancheNames)
    plot(100 * lossGrid, 100 * trancheLossOnNotional(lossGrid, attach(i), detach(i)), "LineWidth", 2.2);
end
xlabel("Collateral par loss fraction (%)");
ylabel("Tranche principal loss / tranche notional (%)");
title("Payoff map: the waterfall turns one pool loss into three kinked tranche losses");
legend(compose("%s [%0.0f%%, %0.0f%%]", trancheNames, 100 * attach, 100 * detach), "Location", "northwest");
grid on;
exportPublicationFigure(fig, fullfile(outputRoot, "clo-payoff-map.png"));

%% Figure 2A: Rho Calibration Objective
% The fitted rho is chosen by matching the cross-cohort variance of default rates.
fig = figure("Color", "white", "Position", [100 100 820 500]);
plot(calibrationGrid.rho, calibrationGrid.objective, "LineWidth", 2.2, "Color", [0.14 0.32 0.72]);
hold on;
xline(rhoHat, "--k", compose("rho-hat = %.3f", rhoHat), "LineWidth", 1.5, "LabelVerticalAlignment", "bottom");
xlabel("Asset correlation rho");
ylabel("Squared variance-fit error");
title("Dependence calibration from repeated cohort default-rate dispersion");
grid on;
exportPublicationFigure(fig, fullfile(outputRoot, "clo-rho-calibration-objective.png"));

%% Figure 2B: Calibration Fit
% The fitted one-factor model should reproduce the observed cohort-rate dispersion.
obsSorted = sort(cohortPanel.default_rate);
mdlSorted = sort(modelImpliedRates);
obsProb = ((1:height(cohortPanel))' - 0.5) / height(cohortPanel);
fig = figure("Color", "white", "Position", [100 100 820 500]);
stairs(100 * obsSorted, obsProb, "LineWidth", 2.0, "Color", "k");
hold on;
stairs(100 * mdlSorted, obsProb, "LineWidth", 2.0, "Color", [0.14 0.32 0.72]);
xlabel("Annual cohort default rate (%)");
ylabel("Empirical CDF");
title("Observed cohort dispersion versus the fitted Vasicek dispersion");
legend("Observed cohort panel", compose("Fitted Vasicek panel (p=%0.2f%%, rho=%0.3f)", 100 * pooledPd, rhoHat), "Location", "southeast");
grid on;
exportPublicationFigure(fig, fullfile(outputRoot, "clo-rho-calibration-fit.png"));

%% Figure 3: Collateral Loss CDF
% Hold marginals fixed and compare only the dependence regime.
plotCdfPair(resultsLow.collateral_loss_path(end, :), resultsHigh.collateral_loss_path(end, :), ...
    "Five-year collateral par loss (%)", ...
    "Same marginals, different dependence: rho mainly changes the tail", ...
    fullfile(outputRoot, "clo-collateral-loss-cdf-low-vs-high.png"));

%% Figures 4A-4C: Tranche Loss Distributions
% Each tranche has its own loss distribution once the waterfall is applied pathwise.
for i = 1:numel(trancheNames)
    plotCdfPair(resultsLow.final_tranche_loss_notional(i, :), resultsHigh.final_tranche_loss_notional(i, :), ...
        compose("%s principal loss / tranche notional (%%)", trancheNames(i)), ...
        compose("%s tranche loss distribution", trancheNames(i)), ...
        fullfile(outputRoot, compose("clo-%s-loss-cdf-low-vs-high.png", lower(trancheNames(i)))));
end

%% Figure 5: Tail Metrics
% Expected loss, VaR, and CVaR show which tranche owns the moved tail mass.
fig = figure("Color", "white", "Position", [100 100 980 540]);
metricNames = ["Expected loss", "VaR 99%", "CVaR 99%"];
metricsLow = [summaryLow.expected_loss_pct, summaryLow.var99_pct, summaryLow.cvar99_pct];
metricsHigh = [summaryHigh.expected_loss_pct, summaryHigh.var99_pct, summaryHigh.cvar99_pct];
barData = [metricsLow, metricsHigh];
bar(barData, "grouped");
set(gca, "XTickLabel", cellstr(trancheNames));
ylabel("Loss metric (% of tranche notional)");
title("Tail metrics move sharply once dependence pushes mass through the tranche kink");
legend("Low rho: Expected loss", "Low rho: VaR 99%", "Low rho: CVaR 99%", ...
       "High rho: Expected loss", "High rho: VaR 99%", "High rho: CVaR 99%", ...
       "Location", "northwest");
grid on;
exportPublicationFigure(fig, fullfile(outputRoot, "clo-tranche-tail-metrics-low-vs-high.png"));

%% Figure 6A: Trigger Frequencies
% Warning triggers are path objects, not static tranche labels.
fig = figure("Color", "white", "Position", [100 100 820 500]);
bar([summaryLow.trigger_frequency_pct, summaryHigh.trigger_frequency_pct], "grouped");
set(gca, "XTickLabel", cellstr(trancheNames));
ylabel("Pathwise trigger breach frequency (%)");
title("Trigger frequencies by tranche");
legend("Low rho", "High rho", "Location", "northwest");
grid on;
exportPublicationFigure(fig, fullfile(outputRoot, "clo-trigger-frequencies-low-vs-high.png"));

%% Figure 6B: Loss-Compensation Spreads
% A compact decision object is the spread needed to absorb simulated principal loss.
fig = figure("Color", "white", "Position", [100 100 820 500]);
bar([summaryLow.loss_compensation_spread_bps, summaryHigh.loss_compensation_spread_bps], "grouped");
set(gca, "XTickLabel", cellstr(trancheNames));
ylabel("Break-even loss-compensation spread (bps)");
title("Loss-compensation spread by tranche");
legend("Low rho", "High rho", "Location", "northwest");
grid on;
exportPublicationFigure(fig, fullfile(outputRoot, "clo-loss-compensation-spread-low-vs-high.png"));

%% Display the Audit Tables
% Print the same compact audit tables used by the chapter prose.
disp("Calibrated rho settings");
disp(scenarioTable);
disp("Tranche summary metrics");
disp(summaryTable);

%% Local Functions
function panel = buildObservedCohortPanel()
% Build a small repeated cohort panel that behaves like a real default-rate extract.
sectors = {"Software","Retail","Healthcare","Energy","Telecom","Services","Industrials","Transport"};
basePd = [0.010, 0.016, 0.012, 0.022, 0.018, 0.015, 0.020, 0.017];
years = (2013:2024)';
trueRho = 0.16;
yearFactor = randn(numel(years), 1);
rows = [];
for y = 1:numel(years)
    for s = 1:numel(sectors)
        cohortSize = randi([110, 220], 1, 1);
        sectorTilt = 0.002 * sin(0.7 * s + 0.4 * y);
        pd1y = min(max(basePd(s) + sectorTilt, 0.006), 0.045);
        conditionalPd = normcdf((norminv(pd1y) - sqrt(trueRho) * yearFactor(y)) / sqrt(1 - trueRho));
        defaults = binornd(cohortSize, conditionalPd);
        rows = [rows; years(y), s, cohortSize, pd1y, defaults, defaults / cohortSize]; %#ok<AGROW>
    end
end
panel = array2table(rows, 'VariableNames', {'year','sector_id','cohort_size','annual_pd','defaults','default_rate'});
panel.sector = string(sectors(panel.sector_id))';
panel = movevars(panel, "sector", "After", "year");
panel.sector_id = [];
end

function [rhoHat, calibrationGrid] = calibrateAssetCorrelation(panel)
% Estimate rho by matching observed and model-implied cohort default-rate variance.
pooledPd = sum(panel.defaults) / sum(panel.cohort_size);
observedVar = var(panel.default_rate, 1);
meanCohortSize = mean(panel.cohort_size);
rhoGrid = linspace(0.01, 0.35, 70)';
modelVar = zeros(size(rhoGrid));
objective = zeros(size(rhoGrid));
for i = 1:numel(rhoGrid)
    rho = rhoGrid(i);
    pairDefault = jointDefaultProbability(pooledPd, rho);
    conditionalVar = pooledPd * (1 - pooledPd) / meanCohortSize;
    commonFactorVar = (1 - 1 / meanCohortSize) * (pairDefault - pooledPd^2);
    modelVar(i) = conditionalVar + commonFactorVar;
    objective(i) = (observedVar - modelVar(i))^2;
end
calibrationGrid = table(rhoGrid, repmat(pooledPd, size(rhoGrid)), repmat(observedVar, size(rhoGrid)), modelVar, objective, ...
    'VariableNames', {'rho','pooled_pd','observed_default_rate_var','model_default_rate_var','objective'});
[~, idx] = min(objective);
rhoHat = rhoGrid(idx);
end

function rates = simulateModelImpliedCohortRates(cohortSizes, pooledPd, rho)
% Simulate one fitted cohort rate per observed cohort size for the validation plot.
systemic = randn(numel(cohortSizes), 1);
conditionalPd = normcdf((norminv(pooledPd) - sqrt(rho) * systemic) / sqrt(1 - rho));
defaults = binornd(cohortSizes, conditionalPd);
rates = defaults ./ cohortSizes;
end

function pool = buildLoanPool()
% Build the heterogeneous loan pool used in the same-marginals experiment.
numLoans = 400;
exposures = lognrnd(0.0, 0.45, numLoans, 1);
weights = exposures / sum(exposures);
annualPd = min(max(betarnd(2.2, 14.0, numLoans, 1) * 0.12, 0.010), 0.060);
annualCpr = min(max(betarnd(2.5, 9.0, numLoans, 1) * 0.18, 0.020), 0.100);
lgd = min(max(0.30 + 0.45 * betarnd(3.0, 3.0, numLoans, 1), 0.30), 0.70);
sectors = ["Software","Retail","Healthcare","Energy","Telecom","Industrials"];
sectorIdx = randi(numel(sectors), numLoans, 1);
pool = table( ...
    compose("L%03d", (1:numLoans)'), ...
    weights, annualPd, annualCpr, lgd, string(sectors(sectorIdx))', ...
    'VariableNames', {'loan_id','weight','annual_pd','annual_cpr','lgd','sector'});
end

function results = runTrancheEngine(pool, attach, detach, triggerLevel, width, rho, numPaths, horizonYears, discountRate)
% Simulate correlated default, prepay, and trigger paths under one rho scenario.
weights = pool.weight';
annualPd = pool.annual_pd';
annualCpr = pool.annual_cpr';
lgd = pool.lgd';
defaultThreshold = norminv(annualPd);

numTranches = numel(attach);
numLoans = height(pool);
active = true(numLoans, numPaths);
outstanding = repmat(width, 1, numPaths);
cumulativeLoss = zeros(1, numPaths);
priorTrancheLossPar = zeros(numTranches, numPaths);
premiumLeg = zeros(numTranches, numPaths);
protectionLeg = zeros(numTranches, numPaths);
triggerAny = false(numTranches, numPaths);
collateralLossPath = zeros(horizonYears, numPaths);
activeCollateralPath = zeros(horizonYears, numPaths);
triggerPath = false(numTranches, horizonYears, numPaths);

for year = 1:horizonYears
    discount = exp(-discountRate * year);
    premiumLeg = premiumLeg + discount * (outstanding ./ width);

    systemic = randn(1, numPaths);
    idiosyncratic = randn(numLoans, numPaths);
    latentAsset = sqrt(rho) .* systemic + sqrt(1 - rho) .* idiosyncratic;
    defaultEvent = active & (latentAsset < defaultThreshold');
    prepayDraw = rand(numLoans, numPaths);
    prepayEvent = active & ~defaultEvent & (prepayDraw < annualCpr');

    defaultLoss = sum((weights' .* lgd') .* defaultEvent, 1);
    recoveryCash = sum((weights' .* (1 - lgd')) .* defaultEvent, 1);
    prepaidPrincipal = sum(weights' .* prepayEvent, 1);

    active = active & ~defaultEvent & ~prepayEvent;
    activeCollateral = sum(weights' .* active, 1);
    cumulativeLoss = cumulativeLoss + defaultLoss;
    collateralLossPath(year, :) = cumulativeLoss;
    activeCollateralPath(year, :) = activeCollateral;

    trancheLossPar = zeros(numTranches, numPaths);
    for i = 1:numTranches
        trancheLossPar(i, :) = trancheLossOnPar(cumulativeLoss, attach(i), detach(i));
    end
    incrementalTrancheLoss = trancheLossPar - priorTrancheLossPar;
    priorTrancheLossPar = trancheLossPar;

    protectionLeg = protectionLeg + discount * (incrementalTrancheLoss ./ width);
    outstanding = max(outstanding - incrementalTrancheLoss, 0.0);

    collections = recoveryCash + prepaidPrincipal;
    for trancheIdx = [3, 2, 1]
        allocation = min(outstanding(trancheIdx, :), collections);
        outstanding(trancheIdx, :) = outstanding(trancheIdx, :) - allocation;
        collections = collections - allocation;
    end

    yearTrigger = cumulativeLoss >= triggerLevel;
    triggerPath(:, year, :) = reshape(yearTrigger, [numTranches, 1, numPaths]);
    triggerAny = triggerAny | yearTrigger;
end

finalTrancheLossPar = priorTrancheLossPar;
finalTrancheLossNotional = finalTrancheLossPar ./ width;
fairSpreadBps = 1e4 * mean(protectionLeg, 2) ./ mean(premiumLeg, 2);

results = struct( ...
    'rho', rho, ...
    'collateral_loss_path', collateralLossPath, ...
    'active_collateral_path', activeCollateralPath, ...
    'trigger_path', triggerPath, ...
    'trigger_any', triggerAny, ...
    'final_tranche_loss_par', finalTrancheLossPar, ...
    'final_tranche_loss_notional', finalTrancheLossNotional, ...
    'fair_spread_bps', fairSpreadBps);
end

function summary = summarizeTranches(results, trancheNames, label)
% Summarize expected loss, tail loss, trigger frequency, and spread by tranche.
numTranches = numel(trancheNames);
scenario = strings(numTranches, 1);
tranche = strings(numTranches, 1);
expectedLoss = zeros(numTranches, 1);
var99 = zeros(numTranches, 1);
cvar99 = zeros(numTranches, 1);
triggerFreq = zeros(numTranches, 1);
spread = zeros(numTranches, 1);
for i = 1:numTranches
    lossSeries = results.final_tranche_loss_notional(i, :);
    q99 = quantile(lossSeries, 0.99);
    expectedLoss(i) = 100 * mean(lossSeries);
    var99(i) = 100 * q99;
    cvar99(i) = 100 * mean(lossSeries(lossSeries >= q99));
    triggerFreq(i) = 100 * mean(results.trigger_any(i, :));
    spread(i) = results.fair_spread_bps(i);
    scenario(i) = label;
    tranche(i) = trancheNames(i);
end
summary = table(scenario, tranche, expectedLoss, var99, cvar99, triggerFreq, spread, ...
    'VariableNames', {'scenario','tranche','expected_loss_pct','var99_pct','cvar99_pct','trigger_frequency_pct','loss_compensation_spread_bps'});
end

function lossPar = trancheLossOnPar(lossFraction, attach, detach)
% Map collateral loss to tranche principal loss on collateral par.
lossPar = min(max(lossFraction - attach, 0.0), detach - attach);
end

function lossNotional = trancheLossOnNotional(lossFraction, attach, detach)
% Express tranche principal loss as a fraction of tranche notional.
lossNotional = trancheLossOnPar(lossFraction, attach, detach) ./ (detach - attach);
end

function pairDefault = jointDefaultProbability(p, rho)
% Compute pairwise joint default under the Vasicek latent Gaussian model.
threshold = norminv(p);
integrand = @(z) normpdf(z) .* normcdf((threshold - sqrt(rho) * z) ./ sqrt(1 - rho)) .^ 2;
pairDefault = integral(integrand, -8, 8, "ArrayValued", true);
end

function plotCdfPair(lowSeries, highSeries, xLabelText, titleText, outPath)
% Draw the same low-rho vs high-rho CDF structure used across the chapter.
lowSorted = sort(lowSeries(:));
highSorted = sort(highSeries(:));
prob = (((1:numel(lowSorted))' - 0.5) / numel(lowSorted));
fig = figure("Color", "white", "Position", [100 100 820 500]);
stairs(100 * lowSorted, prob, "LineWidth", 2.0, "Color", [0.16 0.50 0.38]);
hold on;
stairs(100 * highSorted, prob, "LineWidth", 2.0, "Color", [0.71 0.23 0.17]);
xlabel(xLabelText);
ylabel("CDF");
title(titleText);
legend("Low rho", "High rho", "Location", "southeast");
grid on;
exportPublicationFigure(fig, outPath);
end

function exportPublicationFigure(figHandle, rasterPath, varargin)
% Save each figure as both PNG and SVG for publication use.
exportgraphics(figHandle, rasterPath, varargin{:});
[folderPath, baseName, ~] = fileparts(rasterPath);
svgPath = fullfile(folderPath, baseName + ".svg");
exportgraphics(figHandle, svgPath, "ContentType", "vector");
close(figHandle);
end

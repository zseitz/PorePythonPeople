function consensus = consensusMaker(guessLevs,guesssigs,events,annealParams,varargin)
% Reference consensus building. Takes a reference and events and returns a
% measured consensus. guessLevels should be in units of I/I0

%% Load Aligner
alignerVersion = 3; % new aligner
javastr = version('-java');
if ~exist('aligner', 'var')
    warning('off', 'all');
    JJpath = '/Volumes/Nanopore Share/shared/matlab/JavaJars/';
    javaaddpath(ospath([JJpath 'levelAligner_v' num2str(alignerVersion) ...
        '_java' javastr(8) '.jar']))
    
    warning('on', 'all');
    aligner = levelAligner();
end
%% Options

stepCounts = [1000 50 5 50 5 50 10 1];
modes = 1;
pibad = 0.5;

nIter = floor(annealParams(1)/annealParams(2)) + 2;

mtest = 0.85:0.05:1.15;
btest = -0.03:0.01:0.03;
doalignmentplots = false;

plotlims = [0 1];
updateStepCounts = false;
calibrateAlways = false;
whichLevelsAnneal = 1:length(guessLevs);
whichLevelsCalib = 1:length(guessLevs);
periodicBC = '';
% garbage = false;
for ii = 1:length(varargin)
    if ~ischar(varargin{ii})
        continue
    end
   switch upper(varargin{ii})
       case 'STEPCOUNTS'
           stepCounts = varargin{ii+1}; % Custom Step counts
       case 'CALIBRATEEACHITERATION' % run calibration on every iteration
           calibrateAlways = true;
       case 'MTEST'
           mtest = varargin{ii+1}; %choose a range of slopes to calibrate on
       case 'BTEST'
           btest = varargin{ii+1}; %choose a range of intercepts to calibrate on
       case 'MODES'
           modes = varargin{ii+1}; %customize the types of modes allowed
       case 'DOALIGNMENTPLOTS' 
           doalignmentplots = true; %plot the alignments as they happen
       case 'ANNEALSMALL' %anneal only a certain set of levels
           whichLevelsAnneal = varargin{ii+1}; % Array of levels to anneal
       case 'PIBAD'
           pibad = varargin{ii+1};
       case 'NITER' % number of iterations
           nIter = varargin{ii+1}; %default = T0/dTdt + 2;
       case 'UPDATESTEPCOUNTS'
           updateStepCounts = true;
       case 'OPENSTATE'
           IOS = varargin{ii+1}; % take the average IOS of events to calculate physical units. Assumes events are in I/I0 units
       case 'WHICHLEVELSCALIB'
           whichLevelsCalib = varargin{ii+1}; % choose which Levels to lock the consensus back into place with
%        case 'PERIODIC'
%            periodicBC = 'PERIODICBOUNDARIES';
%        case 'GARBAGE'
%            garbage = 1;
%            whichLevelsGarbage = varargin{ii+1};
       case 'PLOTYLIMS'
           plotlims = varargin{ii+1};
   end
end
%% Initialize
originalEvents = events;
runningCalibration = cell(1,length(events)); % keep a running track of calibration to construct physical units at the end. 
for ii = 1:length(events); runningCalibration{ii} = [1 0];end 
initialTemperature = annealParams(1); % Initialize the temperature
coolingRate = annealParams(2); % rate of cooling
Tnew = initialTemperature;
guesssigs(whichLevelsAnneal) = sqrt(guesssigs(whichLevelsAnneal).^2 + Tnew.^2); % initialize the errors based on the annealing temperature
mapOLD.levels = guessLevs; % initialize the map
mapOLD.sigs = guesssigs;
tcNew = stepCounts; %tc_new is used to iteratively update the step counts (not anymore JMC)
%% Main loop -- do alignments, map building and calibration
for currentIteration = 1:nIter %% loop over 
    disp(strcat('Iteration: ',num2str(currentIteration)))
    disp(strcat('Temperature: ',num2str(Tnew)))
    alignments = cell(1,length(events)); % the alignments for each event
    transitionCounts = cell(1,length(events)); % transition counts for each evnts
    eventCalibration = cell(1,length(events));
    
    for currentEvent = 1:length(events)     
       alignmentsCalib = cell(1,length(mtest)*length(btest)); % Temporarily store the alignments for each calibration test
       scoreCalib = zeros(1,length(mtest)*length(btest)); % the score of the different calibrations bestScoreCalibLocation = min(
       calibrationTemp = cell(1,length(mtest)*length(btest)); % values of the calibration params
       transitionCountsTemp = cell(1,length(mtest)*length(btest)); % empirical transition counts of each event
       mapOLD.levels(isnan(mapOLD.levels)) = guessLevs(isnan(mapOLD.levels));      

       if currentIteration == 1 || calibrateAlways % only calibrate the first iteration of alignments unless othwerwise specified
           count = 0;
           for kk = 1:length(mtest) % calibration loop
                for ll = 1:length(btest) % calibration loop
                    count = count+1;
                    measLevs = events{currentEvent}*mtest(kk) + btest(ll); % Apply the calibration
                        calibrationTemp{count} = [mtest(kk) btest(ll)];                        
                        [alignmentsCalib{count},scoreCalib(count),~,~,~,~,~,~,transitionCountsTemp{count}] = ...
                        levelAlign(measLevs,mapOLD.levels,num2cell(mapOLD.sigs.^-2),...
                         'modedirections',modes,'stepcounts',tcNew,'PIBAD',pibad,'reuse',aligner,periodicBC);    
                 end
            end
       else
           measLevs = events{currentEvent};
           alignmentsCalib = {};
           transitionCountsTemp = {};
           calibrationTemp = {[1 0]};
           [alignmentsCalib{1},scoreCalib,~,~,~,~,~,~,transitionCountsTemp{1}] = ...
                        levelAlign(measLevs,mapOLD.levels,num2cell(mapOLD.sigs.^-2),...
                         'modedirections',modes,'stepcounts',tcNew,'PIBAD',pibad,'reuse',aligner,periodicBC);
       end
       
        [~,bestCalibScoreLocation] = min(scoreCalib); %Pick the best calibration index
%         [~,bestCalibScoreLocation] = max(scoreCalib);
        eventCalibration{currentEvent} = calibrationTemp{bestCalibScoreLocation};            
        runningCalibration{currentEvent}(1) = runningCalibration{currentEvent}(1)*calibrationTemp{bestCalibScoreLocation}(1);
        runningCalibration{currentEvent}(2) = runningCalibration{currentEvent}(2)*calibrationTemp{bestCalibScoreLocation}(1) + calibrationTemp{bestCalibScoreLocation}(2);
        alignments{currentEvent} = alignmentsCalib{bestCalibScoreLocation};   
        transitionCounts{currentEvent} = transitionCountsTemp{bestCalibScoreLocation};
        
        if doalignmentplots %Show the alignment plots
            pause(0.01)
             figure(10);clf;set(gcf,'color',[1 1 1])
             subplot(2,1,1);hold on
             stairs([mapOLD.levels NaN])
             plot(alignments{currentEvent}(alignments{currentEvent}~=0)+0.5,...
                  events{currentEvent}(alignments{currentEvent}~=0)*eventCalibration{currentEvent}(1) +...
                  eventCalibration{currentEvent}(2),'r-*')
             xlim([0 length(guessLevs) + 1])
             ylim(plotlims)
             subplot(2,1,2)
             stairs(events{currentEvent},'r') % plot the event levels
        end
    end
    
    for currentEvent = 1:length(events) %Calibrate all events
        events{currentEvent} = events{currentEvent}*eventCalibration{currentEvent}(1) + eventCalibration{currentEvent}(2);
    end
    eventNEW = events;
        
    if updateStepCounts % Update the transition counts if not annealing     
        if Tnew == 0
            tcNew = zeros(1,length(transitionCounts{1}));
            for currentEvent = 1:length(transitionCounts) 
            tcNew = transitionCounts{currentEvent} + tcNew;
            end
        end
    end
% Build the next generation map    
    
    refLength = length(guessLevs);
    mapNEW.levels = zeros(1,refLength);
    mapNEW.sigs = zeros(1,refLength);
    mapNEW.frequency = zeros(1,refLength);
    mapNEW.frequencyN = zeros(1,refLength); 
    levelsMatrix = NaN*zeros(length(alignments),refLength);
    
    for currentEvent = 1:length(alignments) %Create a matrix where rows are events and columns are reference positions
        for currentPosition = 1:refLength
            alignmentLocationInEvent = find(alignments{currentEvent} == currentPosition,1,'last');
            if ~isempty(alignmentLocationInEvent)
                levelsMatrix(currentEvent,currentPosition) = eventNEW{currentEvent}(alignmentLocationInEvent);            
            end
        end
    end
    
    start = zeros(1,length(alignments)); % Find start point of each event to calculate normalized frequency.
    endpt = zeros(1,length(alignments));
    for ii = 1:length(alignments) 
        if sum(alignments{ii}>0)~=0
        start(ii) = min(alignments{ii}(alignments{ii}~=0));
        endpt(ii) = max(alignments{ii}(alignments{ii}~=0));
        end
    end
    cumulative_start = zeros(1,refLength);
    cumulative_end = zeros(1,refLength);
    for ii = 1:refLength %Find the cumulate of the distribution of starting events
        cumulative_start(ii) = sum(start > ii);
        cumulative_end(ii)   = sum(endpt < ii);
    end

    for ii = 1:refLength  % Calculate the new consensus
        mapNEW.levels(ii) = nanmedian(levelsMatrix(:,ii)); %median keeps spurious alignmnets from overly affecting anything
        mapNEW.sigs(ii) = nanstd(levelsMatrix(:,ii));      
        mapNEW.frequency(ii) = sum(~isnan(levelsMatrix(:,ii)))/length(alignments); %Absolute frequency      
        if (length(alignments) - cumulative_start(ii) - cumulative_end(ii)) > 0.1 %Normalize the frequency based on starting position
            mapNEW.frequencyN(ii) = sum(~isnan(levelsMatrix(:,ii)))/(length(alignments) - cumulative_start(ii) - cumulative_end(ii));
        end
        if isnan(mapNEW.levels(ii)) %if there is no level found use the previous map value in the new map
        mapNEW.levels(ii) = mapOLD.levels(ii);
        end
    end
    
    mapNEW.sigs(mapNEW.sigs < 1e-5) = 1e-5; %Keep the error bars from shrinking arbitrarily small
    mapNEW.sigs(isnan(mapNEW.sigs)) = 1e-3;    

% Update the temperature and calibrate the new map to the old map. Update the calibration

        Tnew = max(initialTemperature - currentIteration*coolingRate,0); %Cool the temperature, but don't go below 0   
        mapNEW.sigs(whichLevelsAnneal) = sqrt(mapNEW.sigs(whichLevelsAnneal).^2 + Tnew^2); 
        
%         if garbage
%             mapNEW.sigs(whichLevelsGarbage) = 10^10;
%         end
        
        aa = guessLevs(whichLevelsCalib);
        bb = mapNEW.levels(whichLevelsCalib);

        pp = polyfit(bb,aa,1); %calibrate new map to original map
        mapNEW.levels = polyval(pp,mapNEW.levels);

        for ii = 1:length(runningCalibration) %fix running calibration and event calibration
        runningCalibration{ii}(1) = pp(1)*runningCalibration{ii}(1);
        runningCalibration{ii}(2) = pp(1)*runningCalibration{ii}(2) + pp(2);
        events{ii} = polyval(pp,events{ii});
        end        
    mapOLD = mapNEW; %Feed the map back into loop
end
%% Map Plots / final output

consensus = mapNEW;
consensus.inputConsensus = guessLevs;
consensus.inputsigs = guesssigs;

consensus.events.calibratedEvents = eventNEW;
consensus.events.uncalibratedEvents = originalEvents;

consensus.alignments = alignments;
consensus.levelsMatrix = levelsMatrix;
consensus.transitionCounts = tcNew;

if exist('IOS','var') % If the IOS exists define physical units
    cal1 = zeros(1,length(runningCalibration)); %get calibration to convert to physical units
    cal2 = zeros(1,length(runningCalibration)); 
    for ii = 1:length(runningCalibration)
        cal1(ii) = runningCalibration{ii}(1);
        cal2(ii) = runningCalibration{ii}(2);
    end

    dcal1 = std(cal1)/sqrt(length(cal1));
    dcal2 = std(cal2)/sqrt(length(cal2));
    cal1 = mean(cal1);
    cal2 = mean(cal2);

    consensus.physicalUnits.m = cal1; %conversions to physical units
    consensus.physicalUnits.dm = dcal1; %conversions to physical units
    consensus.physicalUnits.b = cal2; 
    consensus.physicalUnits.db = dcal2; 
    consensus.physicalUnits.IOS = IOS;
    consensus.physicalUnits.levels = consensus.physicalUnits.IOS*((consensus.levels - consensus.physicalUnits.b)/consensus.physicalUnits.m);
    consensus.physicalUnits.levelsMatrix = consensus.physicalUnits.IOS*((consensus.levelsMatrix - consensus.physicalUnits.b)/consensus.physicalUnits.m);
    consensus.physicalUnits.sigs = consensus.physicalUnits.IOS*((consensus.sigs)/consensus.physicalUnits.m);
    consensus.physicalUnits.README = ' I_phys (pA) = map.physicalUnits.IOS*((map.levels - map.physicalUnits.b)/map.physicalUnits.m)';  
    consensus.physicalUnits.runningCalibration = runningCalibration;
end
consensus.inputs = varargin;
plotConsensusMakerResult(consensus)
end

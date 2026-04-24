function failed = makeJumpsZMS(folders, varargin)

isdc = false;
failed = {};
overwrite = false;
jumpsVersion = 'HDB_2.1_ACTRI';
usedrift = false;
filename_modifier = '';
sensitivity = 9;
minlevellength = 3;
driftval = 0;
flicker_filter = false;
quality_cutoff = 3;
eventName = 'event.mat';
isold = false;

for ca = 1:length(varargin)
    switch upper(varargin{ca})
        case 'DC'
            isdc = true;
            jumpsVersion = 'HDB_2.1_DC';
            flicker_filter = true;
        case 'OVERWRITE'
            overwrite = true;
        case 'DRIFT'
            usedrift = true;
            driftval = varargin{ca+1};
            jumpsVersion = 'HDB_2.1_DRIFT';
        case 'FILENAMEMODIFIER'
            filename_modifier = varargin{ca+1};
        case 'SENSITIVITY'
            sensitivity = varargin{ca+1};
        case 'MINLEVELLENGTH'
            minlevellength = varargin{ca+1};
        case 'FLICKERFILTER'
            flicker_filter = true;
        case 'QUALITYCUTOFF'
            quality_cutoff = varargin{ca+1};
        case 'EVENTNAME'
            eventName = varargin{ca+1};
        case 'OLD'
            isold = true;
    end
end



if ischar(folders)
    folders = {folders};
elseif isobject(folders)
    result = folders;
    folders = folders.folder;
end


for ff = 1:length(folders)
    
    [~, foldername] = fileparts(folders{ff});
    fprintf(['\nWorking on folder ' num2str(ff) '/' num2str(length(folders)) ':  ' foldername])
    
    
    if ~exist([folders{ff} filesep eventName], 'file')
        fprintf('\n       No event structure in folder. Skipping.')
        
        jumps.version = jumpsVersion;
        jumps.eventNum = [];
        jumps.eventTag = [];
        jumps.median = {};
        jumps.std = {};
        jumps.features = {};
        jumps.stiffnesses = {};
        jumps.errors = {};
        jumps.duration = {};
        jumps.numPts = {};
        jumps.reducedStart = {};
        jumps.reducedEnd = {};
        jumps.OS = [];
        
        save([folders{ff} filesep 'jumps.mat'],'jumps')
        
        continue;
    end
    
    load([folders{ff} filesep eventName])
    
    if sum(event.quality == -1) == length(event.quality) && ~isempty(event.quality)
        fprintf('\n       This folder has not been event classified. Skipping.')
        failed{end+1} = folders{ff};
        continue;
    elseif sum(event.quality >= quality_cutoff) == 0
        fprintf('\n       This folder has no good events. Skipping.')
        continue
    end
    
    fprintf('\n       Loading reduced...')
    tic
    load([folders{ff} filesep 'reduced.mat'])
    load([folders{ff} filesep 'meta.mat'   ])
    load([folders{ff} filesep 'oeRed.mat'  ])
    
    if ~overwrite
        
        if exist([folders{ff} filesep 'jumps.mat'], 'file')
            load([folders{ff} filesep 'jumps.mat']);
        elseif exist([folders{ff} filesep 'jumpsAC.mat'], 'file')
            load([folders{ff} filesep 'jumpsAC.mat']);
        elseif exist([folders{ff} filesep 'jumpsSDC.mat'], 'file')
            load([folders{ff} filesep 'jumpsSDC.mat']);
        elseif exist([folders{ff} filesep 'jumps_ian.mat'], 'file')
            load([folders{ff} filesep 'jumps_ian.mat']);
        end
        
    end
    
    if exist('jumps','var') && isfield(jumps, 'appliedcalibration')
        appliedcalibration = jumps.appliedcalibration;
    end
    
    loadingtime = toc;
    fprintf([repmat('\b', 1, length('Loading reduced...')) 'Reduced data with ' num2str(length(reduced.data), 3) ' points loaded in ' num2str(loadingtime, 3) ' seconds.'])
    
    if ~isdc
        acwavelength = reduced.fSamp/meta.acfrequency;
    else
        acwavelength = nan;
    end
    
    clear jumps
    cE = 0;
    
    for ii = 1:length(event.quality)
        if event.quality(ii) >= quality_cutoff
            cE = cE + 1;
            fprintf(['\n       Working on event ' num2str(cE) '/' num2str(sum(event.quality >= quality_cutoff))]);
            
            timepts = event.eventStartNdx(ii):event.eventEndNdx(ii);
            eventdata = reduced.data(timepts);
            tic
            
            if flicker_filter
                badpts = filterFlickers(eventdata);
            else 
                badpts = false(size(eventdata));
            end
            
            orig_ix = 1:length(eventdata);
            eventdata = eventdata(~badpts);
            orig_ix = orig_ix(~badpts);
            
            if isdc && ~usedrift && ~isold
                [transitions, features, errors, stiffnesses] = findLevels(eventdata, 'sensitivity', sensitivity, 'minlevellength', minlevellength);
                starts = transitions(1:end-1)+1;
%                 ends = transitions(2:end);
                starts = orig_ix(starts);
                ends = [starts(2:end)-1 orig_ix(transitions(end))];
            elseif isdc && ~usedrift && isold
                [transitions, features, errors, stiffnesses] = findLevels_old(eventdata, 'sensitivity', sensitivity, 'minlevellength', minlevellength);
                starts = transitions(1:end-1)+1;
%                 ends = transitions(2:end);
                starts = orig_ix(starts);
                ends = [starts(2:end)-1 orig_ix(transitions(end))];
            elseif isdc && usedrift
                [transitions, features, errors, stiffnesses] = findLevelsSetDrift(eventdata, driftval, 'sensitivity', sensitivity, 'minlevellength', minlevellength);
                starts = transitions(1:end-1)+1;
%                 ends = transitions(2:end);
                starts = orig_ix(starts);
%                 ends = orig_ix(ends);
                starts = orig_ix(starts);
                ends = [starts(2:end)-1 orig_ix(transitions(end))];
            elseif ~isdc && ~usedrift
                [transitions, features, errors, stiffnesses] = findLevelsBF(eventdata, 2*pi/acwavelength, 'sensitivity', sensitivity);
                starts = transitions(1:end-1);
%                 ends = transitions(2:end);
                starts = orig_ix(starts);
%                 ends = orig_ix(ends);
                starts = orig_ix(starts);
                ends = [starts(2:end)-1 orig_ix(transitions(end))];
            else
                error('no support yet for drift + AC')
            end
            
            
            calculationtime = toc;
            fprintf(['. Found ' num2str(length(starts)) ' levels in ' num2str(calculationtime, 3) ' seconds.'])
            
            features(1,:) = features(1,:)/oeRed.IOS;
            features(end,:) = features(end,:)/oeRed.IOS;
            errors(1,:) = errors(1,:)/oeRed.IOS;
            errors(end,:) = errors(end,:)/oeRed.IOS;
            
            for cL = 1:length(stiffnesses)
                stiffnesses{cL}(1,1) =  stiffnesses{cL}(1,1)*oeRed.IOS^2;
                stiffnesses{cL}(end,end) =  stiffnesses{cL}(end,end)*oeRed.IOS^2;
            end
            
            jumps.version = jumpsVersion;
            jumps.eventNum(cE) = event.eventNum(ii);
            %jumps.eventTag(cE) = event.category(ii);
            jumps.median{cE} = features(1,:);
            jumps.std{cE} = features(end,:);
            jumps.features{cE} = features;
            jumps.stiffnesses{cE} = stiffnesses;
            jumps.errors{cE} = errors;
            jumps.duration{cE} = (ends - starts + 1) / reduced.fSamp;
            jumps.numPts{cE} = ends - starts + 1;
            jumps.reducedStart{cE} = starts + event.eventStartNdx(ii)-1;
            jumps.reducedEnd{cE} = ends + event.eventStartNdx(ii)-1;
            jumps.OS = oeRed.IOS*ones(size(jumps.eventNum));
        end
    end
    
    if sum( event.quality >= quality_cutoff ) == 0
        jumps.version = jumpsVersion;
        jumps.eventNum = [];
        jumps.median = {};
        jumps.std = {};
        jumps.features = {};
        jumps.stiffnesses = {};
        jumps.errors = {};
        jumps.duration = {};
        jumps.numPts = {};
        jumps.reducedStart = {};
        jumps.reducedEnd = {};
        jumps.OS = [];
    end
    
    if exist('appliedcalibration', 'var')
        jumps.appliedcalibration = appliedcalibration;
    end
    
    save([folders{ff} filesep 'jumps' filename_modifier '.mat'],'jumps')
 
    clear jumps appliedcalibration reduced meta event oeRed starts ends eventvdata eventdata timepts cE acwavelength calculationtime
end




end
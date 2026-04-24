function failedfiles = preprocess(filepaths, varargin)
% Pass a cell array of filepaths to do all preprocessing and create a
% directory with analysis products in the database.
%
% 1. Deal with naming issues - convert paths, create folders, etc.
% 2. Read in the metadata parameters at the header of the .dat file.
% 3. Downsample the data by taking the mean of every so many points.
% 4. Calibrate the int16 data into floating point real current values.
% 5. Use a thresholding algorithm to find event and open states.
% 6. Use a hard filter on time and average current to pre-select events.
% 7. Create meta, hist, reduced, oeRed, and event.
% 8. Extract event features and use a neural network to sort them by
%    quality.
%
% ALL PARAMETERS/OPTIONS
%   Specifier               Default Value   Parameter
%   =====================================================================--
%   'Overwrite'             no overwrite    Whether to overwrite a file.
%
%   'DONOTOVERWRITE'        dont suppress   Whether to suppress the message   
%                                           asking if you want to overwrite
%                                           if overwrite is not specified.
%
%   'IOSguess'              calculated      The guess for the open state
%                                           used for the event finder.
%
%   'IOSbounds'             [90 200]        The bounds in which to search
%                                           for an open state.
%
%   'MinOEDuration'         10              minimum number of points in an
%                                           OE state to be called by the
%                                           event finder.
%
%   'OSThreshold'           0.94            fraction of the IOS that needs
%                                           to be exceeded to classify the
%                                           end of an event.
%
%   'EventThreshold'        0.75            fraction of the IOS that needs
%                                           to be crossed downwards to
%                                           classify the beginning of an
%                                           event.
%
%   'Subfolder'             none            subfolder to save analysis
%                                           products into
%
%
%   'ReducedHz'             5000            frequency of the downsampled
%                                           data
%
%   'EventFilterTime'       1000000         minimum time in microseconds of
%                                           events passed to event.mat
%
%   'EventFilterBounds'     [0.1, 0.75]     bounds on Iave of events passed
%                                           to event.mat, in fraction of
%                                           IOS
%
%   'Flip'                  don't flip      multiplies all the data by -1.
%                                           use this for data taken on
%                                           backwards setups.
%
%   'Vier'                  false           multiplies ONLY current data by
%                                           -1. use this for data taken on
%                                           vier amplifiers.
%
%   'NoOE'                  make oe         don't make an oe or event file
%
%   'SwitchVCOrder'         don't switch    use if you are getting current
%                                           where your voltage should be
%                                           and vice-versa. Switches the
%                                           readin order of the riffled
%                                           voltage-current in the dat
%                                           file.
%
%   'IrmsBounds'            [-inf, inf]     bounds on Irms of events passed
%                                           to event.mat, in fraction of
%                                           IOS.
% 
%   'goBig'                  500MB          modify upper limit on file size.
%                                           Value following goBig will be
%                                           the new limit.
%
%   'forceBounds'            0              if switched on, will force the 
%                                           final open state call to be 
%                                           within the bounds stated in
%                                           IOSbounds
%
%   'FILTERVSTEP'            5              Size of single-datapoint voltage 
%                                           step required to trigger ignoring 
%                                           data for filtering
%
%   'TRANSIENTBUFFER'        2 (ms)         size of window around a voltage 
%                                           change to ignore for filtering purposes
%
%   'AMSYSTEMS'              false          if true, will bypass auto amp detection and
%                                           scale the rawvdata by the 
%                                           output scaling specified in the
%                                           file header. Only valid for AM
%                                           systems amplifiers. Do not use
%                                           with Axopatch data.
%
%   'USEDEHUMMER'            true           run the fftdehummer, normally
%                                           true. May set false for
%                                           exceptionally large data volume
%                                           
%
%
% THINGS CALLED BY PREPROCESS.M THAT ARE NOT MATLAB BUILT-INS
%   Name                What it is/does
%   =====================================================================--
%   databaseUpdate.m    Updates the database directory for use with
%                       databaseNav.
%
%   eventFilter.m       A hard filter to get rid of most garbage, short
%                       states. This consists by default of a minimum time
%                       of 1 second, bounds on the mean current within a
%                       state, and the requirement that it not be an open
%                       state.
%
%   findLocalIOS.m      Finds the local open states of an event. Deals with
%                       special cases such as exponential approach after a
%                       bipolar switch, anomalous open states, and states
%                       occurring at the beginning or end of a file.
%
%   jumpfinder.c        Finds indices corresponding to jumps in a reduced
%                       file using a t-test. Used for level finding.
%
%   rDirName.m          Turns a DAQ output .dat file into the name of the
%                       corresponding analysis folder
%
%   readandreduce.c     Reads in a data file and downsamples by averaging
%                       together every 100 points.
%
%   reduceoec.c         Uses thresholding to find state changes in the
%                       reduced data.
%
%   sortEvent.m         Gives events in a structure quality ratings and
%                       synthesis classifications using the neural network.
%
%   uipickfiles.m       A GUI for picking files. Returns a cell array of
%                       full filepaths.


%Default values:
overwriteflag = 0;
doNotOverwrite = 0; %when flipped to 1, will overwrite the y/n message asking if you want 
                    %to overwrite things.
IOSbounds = [90,200];
MinOEDuration = 10;
OSThreshold = 0.85;
EventThreshold = 0.85;
subfolder = '';
reducedHz = 5000;
eventfiltertime = 1000000;
eventfilterbounds = [0.1, 0.75];
irmsbounds = [-inf, inf];
isvcdaq = 0;
flip = 0;
vier = 0;
makeoe = 1;
switchvcorder = 0;
newdaq = 0;
debugon = 0;
failedfiles.tooBig = {};
failedfiles.noData = {};
failedfiles.badCall = {};
failedfiles.didNotOverwrite = {};
isAC = 0;
goBig = 500;
gobigflag = 0;
vcdaq = 0;
forceBounds = 0;
version = 'LabView_v2.4';
varvoltage = false;
update = true;
vstepThresh = 5; % if the voltage is changed by more tha 5mV in one datapoint;
transientbuffer = 2;% in milliseconds;
amp_flag = false; % flag of whether to check for the amplifier type automatically (false) or manually (true)
useDEHUMMER = true;

for ii = 1:length(varargin)
    switch upper(num2str(varargin{ii}))
        case 'IOSGUESS'
            setIOSguess = varargin{ii+1};
        case 'IOSBOUNDS'
            IOSbounds = varargin{ii+1};
        case 'OVERWRITE'
            overwriteflag = 1;
        case 'DONOTOVERWRITE'
            doNotOverwrite = 1;
        case 'MINOEDURATION'
            MinOEDuration = varargin{ii+1};
        case 'OSTHRESHOLD'
            OSThreshold = varargin{ii+1};
        case 'EVENTTHRESHOLD'
            EventThreshold = varargin{ii+1};
        case 'SUBFOLDER'
            subfolder = [filesep varargin{ii+1} filesep];
        case 'REDUCEDHZ'
            reducedHz = varargin{ii+1};
        case 'EVENTFILTERTIME'
            eventfiltertime = varargin{ii+1};
        case 'EVENTFILTERBOUNDS'
            eventfilterbounds = varargin{ii+1};
        case 'FLIP'
            flip = 1;
        case 'VIER'
            vier = 1;
        case 'NOOE'
            makeoe = 0;
        case 'SWITCHVCORDER'
            switchvcorder = 1;
        case 'IRMSBOUNDS'
            irmsbounds = varargin{ii+1};
        case 'NEWDAQ'
            newdaq = 1;
        case 'DEBUG'
            debugon = 1;
        case 'AC'
            reducedHz = 50000;
            if length(varargin) > ii && isnumeric(varargin{ii+1})
                reducedHz = varargin{ii+1};
            end
            isAC = 1;
        case 'GOBIG'
            gobigflag = 1;
            goBig = varargin{ii+1};
        case 'FORCEBOUNDS'
            forceBounds = 1;
        case 'VARVOLTAGE'
            varvoltage = true;
        case 'NOUPDATE'
            update = false;
        case 'RAILEDDATA'
            railVal = varargin{ii+1};
        case 'FILTERVSTEP' %Size of single-datapoint voltage step required to trigger ignoring data for filtering
            vstepThresh = varargin{ii+1};
        case 'TRANSIENTBUFFER' %size of window around a voltage change to ignore for filtering purposes
            transientbuffer = varargin{ii+1};
        case 'AMSYSTEMS'
            amp_flag = true;
            isAM = varargin{ii+1}; % set to true if data is from an AM systems amp (in which case we need to scale the vdata)
        case 'DEHUMMER'
            useDEHUMMER = varargin{ii+1};
    end
end


%handle the filepath list input. We ultimately want a cell array of
%folders.
if ischar(filepaths)
    filepaths = {filepaths};
elseif isobject(filepaths)
    if isempty(filepaths.data) %if they pass an object with no .data field, they probably 
                               %accidentally passed a database result.
        fprintf(['\n\nFAILURE: You passed a database result. This is\n'...
                 'wrong. Pass raw data files by using the search term\n'...
                 '''#data'' in dataNavi.\n\n']);
        failedfiles.badCall = filepaths;
        return;
    else
        filepaths = filepaths.data;
    end
end

startpath = pwd;
datapath = '/Volumes/Phys-Nanostore/shared/matlab/experiment/Database/Data/';
% Loop over all files passed.
for k = 1:length(filepaths)
    
    
    fprintf('---------------------------------------------------------------------\n')
    
    
    %% Get situated for reading data.
    
    
    filepath = filepaths{k};
    [pathname,thedate] = rDirName(filepath);
    
    fprintf([num2str(k) '/' num2str(length(filepaths)) ' - Working on ' pathname '. '])
    
        
        % If there is no directory, make one.
        if ~exist(ospath([datapath '20' thedate(1:2) '/' pathname subfolder]), 'dir')
            mkdir(ospath([datapath '20' thedate(1:2) '/' pathname subfolder]))
            
            % If there is already a directory, and overwriteflag is 0, warn
            % about overwriting the old preprocess output.
        elseif overwriteflag == 0 && doNotOverwrite == 0
            beep;
            inputstring = input(['\n The file ' pathname ', or an identically named '...
                'one, has already been processed.\n Are you sure you want to continue '...
                'and overwrite the old results (y/n)? \nTo suppress this prompt in '...
                'the future, include the input option ''overwrite'' or '...
                '''donotoverwrite'' depending on what default behaviour you want. '], ...
                's');
            % Skip to the next file if they say no. Any other input
            % continues on to rewrite the output.
            if inputstring == 'n'
                failedfiles.didNotOverwrite{end+1, 1} = filepath;
                continue
            end
        elseif doNotOverwrite == 1
            % Skip to the next file if they say no. Any other input
            % continues on to rewrite the output.
            failedfiles.didNotOverwrite{end+1, 1} = filepath;
            continue
        end
    
    %% Read everything in.
    
    % Read in the metadata. This defines station, alpha, beta, f3dB, fSamp,
    % voltage, Coeff0-3, RAW_DAQ_DC_OFFSET, and fileNum, and brings us to
    % the beginning of the data proper.
    %
    % All of the defining statments (e.g. 'alpha=10;') are written on their
    % own lines at the top of the DAQ output file. So we iterate through
    % each of these lines and evaluate them in matlab.
    %
    % 'station' is exceptional, because we want to define a station to
    % be just the first letter of the string defining the station in the
    % header, in order to later use it to differentiate between normal and
    % voltage control setups. Voltage control setups have station letter
    % "VC", which we read in as "V".
    %
    % Alpha and beta are special cases because 'alpha' and 'beta' are
    % predefined matlab functions. These are instead named "ALPHA" and
    % "BETA".
    
    file = fopen(ospath(filepath), 'rb');
    
    while 1
        str = fgetl(file); %Get one line of the file.
        if strcmpi(str(1:5), 'alpha') %Check to see if the first five letters of the 
                                      %line are 'ALPHA'
            ALPHA = 10; %If so, set ALPHA equal to X in the line 'ALPHA = X'
        elseif strcmpi(str(1:4), 'beta') %same for beta
            BETA = str2double(str(6:end-1));
        elseif strcmpi(str(1:7), 'station') %same for station
            station = str(9); %but only get the first line of station
        elseif strcmpi(str(1:7), 'version') %check the version (LabView or LabWindows)
            version = str(9:end-1);
        elseif strcmpi(str(1:7),'filenum')
            eval(str);
            break
        else
            eval(str);
        end
    end
    
    % Calculate the downsampling rate required to get the sampling
    % frequency to reducedHz.
    downsamplerate = fSamp/reducedHz;
    
    % Boolean value saying whether it is a voltage control experiment.
    % 0 = not VC, 1 = VC. In string form because
    isvoltagecontrol = (station == 'V' | vcdaq == 1 | isvcdaq == 1);
    if newdaq
        isvoltagecontrol = 1;
    end
    
    
    % Find the start position of the data (i.e. the end of the topmatter)
    % and the total number of points in the file. L is the length divided
    % by two because the file is composed of int16's, which are two bytes
    % long.
    startposition = ftell(file);
    fseek(file, 0, 'eof');
    L = floor((ftell(file) - startposition)/2);
    fclose(file);
    numMB = L*2/1048576;
    
    %if the file is empty, return a failure.
    if L<=0
        fprintf('\n\nFAILURE: No data in file.\n\n')
        failedfiles.noData{end+1, 1} = filepath;
        continue
    
    %if the data is too big, return a failure
    elseif numMB > goBig && gobigflag == 1
        fprintf(['\n\nFAILURE: File (' num2str(numMB) ' MB) too large for comfort. '...
            'Consider\nsplitting the file using splitRawDataFile.m.\n\n'])
        failedfiles.tooBig{end+1, 1} = filepath;
        continue
    elseif numMB > 500 && gobigflag == 0
        fprintf(['\n\nFAILURE: File (' num2str(numMB) ' MB) too large for comfort. '...
            'Consider\nsplitting the file using splitRawDataFile.m.\n\n'])
        failedfiles.tooBig{end+1, 1} = filepath;
        continue
    end
    
    
    fprintf([num2str(numMB, 3) ' MB.\n']) % Big number is bytes in one megabyte
    fprintf('Reading... ')
    
    %read the data in in chunks of no more than 1M at a time for
    %performance reasons and easy abortion.
    fid = fopen(ospath(filepath));
    fseek(fid, startposition, 'bof');
    totalread = 0;
    rawdata = zeros(1,L);
    while totalread < L
        printstring = [num2str(totalread/L * 100, 2) '%%'];
        fprintf(printstring)
        readthistime = min(10000000, L - totalread);
        rawdata(totalread+1:totalread+readthistime) = fread(fid, readthistime, 'short')';
        fprintf(repmat('\b',1,length(printstring)-1));
        totalread = totalread + readthistime;
    end
    
    %the data is recorded riffled with alternating I/V points
    rawvdata = rawdata(2:2:end);
    rawidata = rawdata(1:2:end);
    
    
    
    % Combine the data into one array if it is not a VC experiment.
    if ~isvoltagecontrol
        rawidata = rawdata;
    end

    % if data is from the AM systems amp, divide the voltage by the output
    % scaling recorded in the file header

    if ~amp_flag % automatically check for output scaling to decide which amp the data is from
        
        if exist("OutputScaling",'var')
           rawvdata = rawvdata./OutputScaling;
           fprintf('\b\b\b\b\b\b\b - Output scaling found - processing data from AM Systems amp)')
            isAM = true;
        else 
            isAM = false;
            fprintf('\b\b\b\b\b\b\b - Processing data from Axopatch amp)')
        end

    else % manually select amp 

        if isAM % if AM systems was manually selected
            if exist("OutputScaling",'var') % Make sure Output Scaling variable exists!
                rawvdata = rawvdata./OutputScaling;
                fprintf('\b\b\b\b\b\b\b - Output scaling found - processing data from AM Systems amp)')
            else
                error('Indicated AM systems amp, but output scaling not found in file header. Aborting...')
            end
        else % if axopatch was manually selected
            if exist("OutputScaling",'var') % Output Scaling variable shouldn't exist if data is from an axopatch
                warning('OutputScaling exists as a variable, but isAM was not selected. Skipping voltage scaling')
            else
                fprintf('\b\b\b\b\b\b\b - Processing data from Axopatch amp)')
            end
        end
    end

    %remove fourier spectrum spikes
    
    %not really "downsampling" in the tradition sense of decimation; rather, mean together 
    %every (rate) points to obtain a signal whose size has been reduced by a factor of 
    %1/(rate).

    %create an 8-pole butterworth filter
    fprintf('\b\b\b\b\b\b\b - Filtering... ')
    dehumbatchsize = 5e5;
    idata = rawidata;
    vtransitions = [1 find(abs(diff(rawvdata))>(vstepThresh*(ALPHA*BETA)/1000/Coeff1-Coeff0)) length(rawidata)];
    for ii = 1:length(vtransitions)-1
        chunkix = vtransitions(ii)+ceil(transientbuffer*fSamp/1000):vtransitions(ii+1)-ceil(transientbuffer*fSamp/1000);
        if ~isempty(chunkix)    
            if useDEHUMMER
            idata(chunkix) = fftdehum(rawidata(chunkix),201,2.2); % (data chunk,dehum window in the FFT=201, and threshold for "peaks" to be knocked down = 2)
            end
        end
    end
    

    fprintf('\b\b\b\b\b\b\bed - Downsampling... ')
    if downsamplerate > 1
        [b,a] = butter(4,2/downsamplerate);

        idata = fliplr(filter(b,a,fliplr(filter(b,a,idata))));
        idata = idata(1:downsamplerate:end);
        if isvoltagecontrol
            vdata = filter(b,a,rawvdata);
            vdata = vdata(1:downsamplerate:end);
        end
    else
        idata = rawidata;
        if isvoltagecontrol
            vdata = rawvdata;
        end
    end
    clear rawdata rawidata rawvdata
    
    %at some point we were having a problem with current unreliably being
    %the first element in the data file. This option swaps which subset of
    %the data is the voltage and the current.
    if switchvcorder
        temp = idata;
        idata = vdata;
        vdata = temp;
    end
    
    %if running a setup at a negative clamp voltage for an entire experiment, we might 
    %want to put a minus sign on everything.
    if flip
        idata = -idata;
        vdata = -vdata;
        voltage = -voltage;
    end
    
    % if running on a vier amplifier, flip ONLY the current
    if vier
        idata = -idata;
    end
    
    
    
    
    %% Calibrate the data.
    
    fprintf('\b\b\b\b\b\b\bed - Calibrating...')
    
    % This turns the int16 data from the DAQ into real-life current values.
    idata = (Coeff0 + Coeff1 * idata + Coeff2 * idata.^2)*1000/(ALPHA * BETA);
    if isvoltagecontrol
    vdata = (Coeff0 + Coeff1 * vdata + Coeff2 * vdata.^2)*1000/(ALPHA * BETA);
    end
    if debugon
        idata = idata(1:1e7);
        if isvoltagecontrol
            vdata = vdata(1:1e7);
        end
    end
    
    %% Make all the files except event.
    
    
    
    %Go to the pore's folder in the Database.
    cd(ospath([datapath '20' thedate(1:2) '/' pathname subfolder]))

    
    %========================================================================%
    
    fprintf('\b\b\b\b\b\bed\nMaking meta...')
    
    % Construct "meta".
    
    % These are all from the header of the DAQ file.
    
    clear meta
    
    meta.station = station;
    meta.alpha = ALPHA;
    meta.beta = BETA;
    meta.f3db = f3dB;
    meta.fSamp = fSamp;
    meta.voltage = voltage;
    meta.Coeff0 = Coeff0;
    meta.Coeff1 = Coeff1;
    meta.Coeff2 = Coeff2;
    meta.Coeff3 = Coeff3;
    meta.version= version;
    meta.RAW_DAQ_DC_OFFSET = RAW_DAQ_DC_OFFSET;
    if isAM
        meta.OutputScaling = OutputScaling; % add the output scaling parameter to the meta data if using an AM systems amp
    end


    % These are all simple calculations with self-explanatory names.
    meta.dataStartByte = startposition;
    meta.file = filepath;
    meta.bytes = L*2+startposition;
    meta.numpts = L;
    meta.duration = L/fSamp;
    
    freqendpt = strfind(upper(filepath),'HZ')-1;
    if ~isempty(freqendpt)
        ii = freqendpt-1;
        while isstrprop(filepath(ii), 'digit')
            freqstartpt = ii;
            ii = ii-1;
        end
        acfrequency = str2double(filepath(freqstartpt:freqendpt));
        meta.acfrequency = acfrequency;
    end
    
    
    
    % These might or might not exist in the header. Use default values
    % if they don't.
    if exist('Vmin', 'var')
        meta.Vmin = Vmin;
    else
        meta.Vmin = -10;
    end
    if exist('Vmax', 'var')
        meta.Vmax = Vmax;
    else
        meta.Vmax = 10;
    end
    % Sampling interval- number of microseconds between points.
    meta.sampInt = 1e6/fSamp;
    meta.endPt = (meta.bytes-meta.dataStartByte)/2;
    
    save('meta.mat', 'meta')
    
    
    %========================================================================%
    
    
    % Construct "reduced".
    
    fprintf('\b\b\b - reduced...')
    
    clear reduced
    
    reduced.fSamp = reducedHz;
    
    reduced.f3dB = reduced.fSamp;   % f3dB is just the reduced sampling
    % frequency, since this is our new hard
    % cutoff frequency.
    
    reduced.filter = NaN;           % There is no more filter.
    reduced.data = idata;
    if isvoltagecontrol
        reduced.vdata = vdata;
    end
    reduced.pt = (1:length(idata))*downsamplerate;
    
    save('reduced.mat', 'reduced', '-v7.3')
    
    
    
    %========================================================================%
    
    
    % Construct "hist".
    
    fprintf('\b\b\b - hist...')
    
    clear hist
    
    hist.x = -1000:.1:1000;
    hist.y = histc(idata, hist.x)';
    if isvoltagecontrol
        hist.yV = histc(vdata, hist.x)';
    end
    save('hist.mat', 'hist')
    
    
    %========================================================================%
    
    % Construct "oeRed"
    
    fprintf('\b\b\b - oeRed...')
    
    %if we don't want to make oeRed or event files
    if ~makeoe
        
        clear oeRed event reduced meta hist output idata vdata cmdstr IOSguess
        fclose('all');
        
        fprintf('\b\b\b - Done.\n')
        
        continue
    end
    
    
    clear oehist
    
    
        
    %if it's AC, we need to downsample to the waveform frequency, since it is easiest to 
    %identify events by ignoring any AC component.
    if isAC
        ac_ds_rate = round(reduced.fSamp/acfrequency);
        oetime = round(downsampleinmatlab(1:length(reduced.data), ac_ds_rate));
        oedata = downsampleinmatlab(reduced.data(1:length(reduced.data)), ac_ds_rate);
    elseif ~exist('vdata', 'var') || varvoltage
        oetime = 1:length(reduced.data);
        oedata = reduced.data(oetime);
    else %excise data at other-than-nominal voltages
        if flip
            oetime = find(abs(vdata - (-meta.voltage)) < 5); 
        else
            oetime = find(abs(vdata - meta.voltage) < 5); 
        end
            if isempty(oetime)
                if flip
                    warning('WARNING: your reduced.vdata does not match meta.voltage to within 3 mV, performing oe on data where vdata is within 10 mV of meta.voltage')
                    oetime = find(abs(vdata - (-meta.voltage)) < 10);
                else
                    warning('WARNING: your reduced.vdata does not match meta.voltage to within 3 mV, performing oe on data where vdata is within 10 mV of meta.voltage')
                    oetime = find(abs(vdata - meta.voltage) < 10);
                end
            end
        oedata = reduced.data(oetime);
    end
    
    oehist.x = hist.x;
    oehist.y = hist.y;

    
    % Find an IOSguess based on histogram data if no guess is provided in
    % the input. Uses the current with the maximum value within IOSbounds
    % on the smoothed histogram within IOSbounds.
    if exist('setIOSguess','var')
        IOSguess = setIOSguess;
    else
        [~, whereIOSguess] = max( smooth( oehist.y( oehist.x > IOSbounds(1) & oehist.x<IOSbounds(2) ) ) );
        whereIOSguess = find(oehist.x > IOSbounds(1), 1, 'First')+whereIOSguess;
        IOSguess = oehist.x(whereIOSguess);
    end
    
    %locate events with simple thresholding method. transitionpts is location of 
    %transitions, oe is boolean array of 0 (open) or 1 (event)
    [transitionpts,oe] = findOEtransitions(oedata,IOSguess, ...
        MinOEDuration,OSThreshold,EventThreshold, 1);
   


    %identify whichdata points are in the open state
    dataisOS = false(1,length(oedata));
    for ii = 1:length(transitionpts)-1
        if ~oe(ii)
            dataisOS(transitionpts(ii):transitionpts(ii+1)) = true;
        end
    end
    osdata = oedata(dataisOS);
    
    %re-index to fix locations given the excised data
    transitionpts = oetime(transitionpts);
    transitionpts(1) = 1;
    transitionpts(end) = length(idata);
    
    
    clear oeRed
    
    %build oeRed
    oeRed.startNdx = transitionpts(1:end-1);
    oeRed.endNdx = transitionpts(2:end);
    oeRed.state = oe; % 1 = event, 0 = open state
    oeRed.duration = diff(transitionpts) / reducedHz * 1000000; %in microseconds
    oeRed.Imin = 0*oeRed.startNdx;
    oeRed.Imax = 0*oeRed.startNdx;
    oeRed.Iave = 0*oeRed.startNdx;
    oeRed.Imed = 0*oeRed.startNdx;
    oeRed.Irms = 0*oeRed.startNdx;
    
    for zz = 1:length(oeRed.startNdx)
        oeRed.Imin(zz) = min(reduced.data(oeRed.startNdx(zz):oeRed.endNdx(zz)));
        oeRed.Imax(zz) = max(reduced.data(oeRed.startNdx(zz):oeRed.endNdx(zz)));
        oeRed.Iave(zz) = mean(reduced.data(oeRed.startNdx(zz):oeRed.endNdx(zz)));
        oeRed.Imed(zz) = median(reduced.data(oeRed.startNdx(zz):oeRed.endNdx(zz)));
        oeRed.Irms(zz) = std(reduced.data(oeRed.startNdx(zz):oeRed.endNdx(zz)));
    end
    
    oeRed.startPt = reduced.pt(oeRed.startNdx);
    oeRed.endPt = reduced.pt(oeRed.endNdx);

    %calculate the open state mean and standard deviation
    if ~forceBounds
        oeRed.IOS = median(osdata(abs(osdata - mean(osdata)) < std(osdata)*3));
    elseif forceBounds
        osdata = osdata(osdata>IOSbounds(1) & osdata<IOSbounds(2));
        oeRed.IOS = median(osdata(abs(osdata-mean(osdata)) < std(osdata)*3));
    end
    
    oeRed.sigmaOS = std(osdata);
    
    
    oeRed.numEvents = length(oeRed.state(oeRed.state==1));
    
    oeRed.criteria.IOSguess = IOSguess;
    oeRed.criteria.MinOEDuration = MinOEDuration;
    oeRed.criteria.OSThreshold = OSThreshold;
    oeRed.criteria.EventThreshold = EventThreshold;
    
    save('oeRed.mat', 'oeRed')
    
    
    %========================================================================%
    
    
    % Construct "event".
    
    fprintf('\b\b\b\nFiltering oeRed...');
    
    % Use the eventFilter to perform a hard filtering of events in oeRed. 
    goodevents = eventFilter(oeRed, 'MinTime', eventfiltertime, 'IaveBounds', eventfilterbounds, 'Irmsbounds', irmsbounds);
    
    
    fprintf('\b\b\b - Making event...');
    
    % Thee are all just the stats of the good events cherry picked from
    % oeRed.
    
    clear event
    
    event.eventNum = goodevents;
    
    
    
    event.eventStartNdx = oeRed.startNdx(goodevents);
    event.eventEndNdx = oeRed.endNdx(goodevents);
    event.eventStartpt = oeRed.startPt(goodevents);
    event.eventEndpt = oeRed.endPt(goodevents);
    event.eventDur = oeRed.duration(goodevents);
    event.eventIave = oeRed.Iave(goodevents);
    event.eventImin = oeRed.Imin(goodevents);
    event.eventImax = oeRed.Imax(goodevents);
    event.eventIrms = oeRed.Irms(goodevents);
    event.localIOS = oeRed.IOS*ones(size(event.eventNum));
    
    
    % Quality/synthesis of -1 means no quality or synthesis score has been
    % determined yet.
    event.quality = -1*ones(1, length(goodevents));
    event.synthesis = -1*ones(1, length(goodevents));
    event.hardfilter.MinTime = eventfiltertime;
    event.hardfilter.IaveBounds = eventfilterbounds;
    event.hardfilter.IrmsBounds = irmsbounds;
    
    save('event.mat', 'event')
    
    
    
    
    %% Wrap up
    
    
    fclose('all');
    
    
    
    fprintf('\b\b\b - Done.\n')
    
    clear oeRed event reduced meta hist output idata vdata cmdstr IOSguess transitionpts vslope  vmean imedian idatachunk ix toremove oetime oevdata oedata transientlength vtransitions meanleveli osdata std_of_end oehist onevoltagepts goodevents
    
    
    
end

fprintf('=====================================================================\n')

% Go back to where we were when we ran the function, and update the database.
cd(startpath);

if update
databaseMod('update');
end

fprintf('\nAll done!\n\n\n')

end
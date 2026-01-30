# PorePythonPeople
Developing python based Nanopore Sequencing/Tweezing analysis pipeline

The first function that we will try to port into Python from MATLAB will be the eventclassifier function.

This code takes preprocessed sequencing data (Current in picoamperes, by points) which can be converted to current 
by time assuming that we know what the sampling frequency was set to at the time of recording data. In general, sampling
frequency, or "fsamp" as it is commonly referred to in this script, should be 10kHz. This means that for every 10k points,
1 second goes by.

Below is the code for eventclassifier.m in MATLAB:



%
%
%
%
%
%
%
%



function eventclassifier(folders,varargin)

%Modified Eventclassifier
%Mod by Kenji 150616
%
%KEYSTROKES
%
%RATING EVENTS
%
% Z   Assign Quality 3
%
% X   Assign Quality 2
%
% C   Assign Quality 1
%
% V   Assign Quality 0
%
% T   Category Tag Select (1-9)
%
% UPARROW Synthesis Yes
%
% DOWNARROW Synthesis No
%
% N   Next Folder
%
% P   Previous Folder
%
% R+(Z,X,C or 1-9)  Rewind to last Quality or Category chosen
%
% F+(Z,X,C,B or 1-9)   FastForward to next Quality or Category chosen (B
% for unclassified events)
%
% M+M   Merge current event with subsequent event
%
% S+Follow directions+S   Split Event
%
% Q+Q(Esc)   Quit E-classifier



fold = folders;
isac = 0;

userDownsample = false;
 for ii = 1:length(varargin)
     switch upper(varargin{ii})
          case 'DOWNSAMPLERATE'
              userDownsample = true;
              dsr = varargin{ii+1};
     end
 end

if ~iscell(folders)
    if ischar(folders)
        folders = {folders};
    elseif isobject(folders)
        folders = folders.folder;
    end
end



currentfolder = 1;
currentevent = 1;
qualitycolors = [0 0 0; 0.8 0 0; 0.6 0.3 0; 0.3 0.6 0; 0 0.9 0];
events = cell(size(folders));
IOSs = cell(size(folders));
reducedfSamps = zeros(size(folders));
dsrates = zeros(size(folders));
dsdatas = cell(size(folders));
ds_eventStartNdxs = cell(size(folders));
ds_eventEndNdxs = cell(size(folders));
eventlengths = cell(size(folders));
dcdsfreq = 500;



fig = figure('Position', [100, 100, 1400, 700]);

msg = '';
for ii = length(folders):-1:1
    
    fprintf(repmat('\b', 1, length(msg)));
    msg = ['Loading and downsampling folder ' num2str(length(folders)-ii+1) '/' num2str(length(folders)) '. Please wait.'];
    fprintf(msg)
    
    try
        load([folders{ii} filesep 'event.mat']);
        load([folders{ii} filesep 'reduced.mat']);
        load([folders{ii} filesep 'meta.mat']);
        if isac, load([folders{ii} filesep 'oeJava.mat']); end
    catch
        event.eventNum = [];
    end
    if isempty(event.eventNum)
        folders(ii) = [];
        dsrates(ii) = [];
        dsdatas(ii) = [];
        ds_eventStartNdxs(ii) = [];
        ds_eventEndNdxs(ii) = [];
        eventlengths(ii) = [];
        events(ii) = [];
        IOSs(ii) = [];
        reducedfSamps(ii) = [];
        continue
    end
    
    
    %Find the downsampling frequency
    if isfield(meta, 'acfrequency')
        dsrates(ii) = round(reduced.fSamp / meta.acfrequency);
    elseif ~userDownsample
        dsrates(ii) = reduced.fSamp/dcdsfreq;
    else
        dsrates(ii) = dsr;
    end
    
    %Get and downsample the data. Re-index start and ends.
    dsdatas{ii} = downsampleinmatlab(reduced.data, dsrates(ii));
    ds_eventStartNdxs{ii} = round(event.eventStartNdx/dsrates(ii));
    ds_eventEndNdxs{ii} = round(event.eventEndNdx/dsrates(ii));
    eventlengths{ii} = ds_eventEndNdxs{ii}-ds_eventStartNdxs{ii};
    events{ii} = event;
    if ~isfield(event,'category')
        events{ii}.category = zeros(1,length(event.quality));
    elseif length(event.quality)~=length(event.category)
        events{ii}.category = zeros(1,length(event.quality));
    end
    if isac
        IOSs{ii} = setIOS*ones(1, length(event.eventNum));
    else
        IOSs{ii} = event.localIOS;
    end
    
    reducedfSamps(ii) = reduced.fSamp;
    
end

%Start edit KMD 151027
%Creating an array to grab folder names here
showfold = {};
for ll = 1:length(folders)
    folly = regexp(folders{ll},'[\/]','split');
    showfold{end+1} =  folly{length(folly)};
end
%End edit

fprintf('\n')
if isempty(ds_eventStartNdxs)
    error('No properly processed folders in list, or no events in any folder')
end
while true
    
    
    
    %Plot the current event.
    
    clf, hold on, set(gca,'ytick',0:10:200,'ygrid','on','fontsize',16)
    
    plotix = max(1, ds_eventStartNdxs{currentfolder}(currentevent)-round(eventlengths{currentfolder}(currentevent)/20)):min(length(dsdatas{currentfolder}), ds_eventEndNdxs{currentfolder}(currentevent) + round(eventlengths{currentfolder}(currentevent)/20));
    plot( plotix * dsrates(currentfolder) / reducedfSamps(currentfolder), dsdatas{currentfolder}(plotix) )
    plot([plotix(1), plotix(end)] * dsrates(currentfolder) / reducedfSamps(currentfolder), IOSs{currentfolder}(currentevent)*[1 1], '--r')
    try
        axis([plotix(1) * dsrates(currentfolder) / reducedfSamps(currentfolder), plotix(end) * dsrates(currentfolder) / reducedfSamps(currentfolder), 0, IOSs{currentfolder}(currentevent)*1.15]);
    catch
        disp('ok')
    end
    titlename = ['F:' num2str(currentfolder) '/' num2str(length(showfold)) ',' showfold{currentfolder} ', event ' num2str(currentevent) '. Dur = ' ...
        num2str(eventlengths{currentfolder}(currentevent)*dsrates(currentfolder)/reducedfSamps(currentfolder)) ' s, Q = ' ...
        num2str(events{currentfolder}.quality(currentevent)) ', S = ' num2str(events{currentfolder}.synthesis(currentevent)) ', Cat = ' num2str(events{currentfolder}.category(currentevent)) '.'];
%     titlename = ['F:' num2str(currentfolder) '/' num2str(length(showfold)) ',' showfold{currentfolder} ', event ' num2str(currentevent) '. Dur = ' ...
%         num2str(eventlengths{currentfolder}(currentevent)*dsrates(currentfolder)/reducedfSamps(currentfolder)) ' s, Q = ' ...
%         num2str(events{currentfolder}.quality(currentevent)) ', S = ' num2str(events{currentfolder}.synthesis(currentevent)) ', Cat = ' num2str(events{currentfolder}.category(currentevent)) '.'];
title(titlename, 'color', qualitycolors(events{currentfolder}.quality(currentevent) + 2, :),'Interpreter','none','fontsize',10)
hold on;
line([events{currentfolder}.eventStartNdx(currentevent)/reducedfSamps(currentfolder), events{currentfolder}.eventStartNdx(currentevent)/reducedfSamps(currentfolder)],[0 IOSs{currentfolder}(currentevent)],'color','r')
line([events{currentfolder}.eventEndNdx(currentevent)/reducedfSamps(currentfolder), events{currentfolder}.eventEndNdx(currentevent)/reducedfSamps(currentfolder)],[0 IOSs{currentfolder}(currentevent)],'color','r')
newplot = 0;

%Only do the plotting part if we've gone to a new event. Otherwise stay
%in this loop.
while ~newplot
    
    %TAKE INPUT
    
    %Wait for a non-click keypress.
    w = 0;
    while w == 0
        w = waitforbuttonpress;
    end
    
    inputt = double(upper(fig.CurrentCharacter));
    if ~(isstr(inputt)||isscalar(inputt))
        inputt = -100 ;
    end
    %Switch on input
    switch inputt
        
        %Horizontal arrows go forward or back one event.
        case 28 %left arrow
            currentevent = currentevent - 1;
            newplot = 1;
        case 29 %right arrow
            if events{currentfolder}.quality(currentevent) == 3;
                donothing = 1;
            elseif events{currentfolder}.quality(currentevent) == 2;
                donothing = 1;
            elseif events{currentfolder}.quality(currentevent) == 1;
                donothing = 1;
            else
                events{currentfolder}.quality(currentevent) = 0;
                event = events{currentfolder};
                save([folders{currentfolder} filesep 'event.mat'], 'event');
                clear event
            end
            currentevent = currentevent + 1;
            newplot = 1;
            
            %Vertical arrows set synthesis, save, and reprint the title.
        case 30 %up arrow
            events{currentfolder}.synthesis(currentevent) = 1;
            event = events{currentfolder};
            save([folders{currentfolder} filesep 'event.mat'], 'event');
            clear event
            titlename = ['F:' num2str(currentfolder) '/' num2str(length(showfold)) ',' showfold{currentfolder} ', event ' num2str(currentevent) '. Dur = ' ...
                    num2str(eventlengths{currentfolder}(currentevent)*dsrates(currentfolder)/reducedfSamps(currentfolder)) ' s, Q = ' ...
                    num2str(events{currentfolder}.quality(currentevent)) ', S = ' num2str(events{currentfolder}.synthesis(currentevent)) ', Cat = ' num2str(events{currentfolder}.category(currentevent)) '.'];
            title(titlename,'fontsize',12, 'color', qualitycolors(events{currentfolder}.quality(currentevent) + 2, :));
        case 31 %down arrow - mark synthesis = 0, save, reprint title
            events{currentfolder}.synthesis(currentevent) = 0;
            event = events{currentfolder};
            save([folders{currentfolder} filesep 'event.mat'], 'event');
            clear event
            titlename = ['F:' num2str(currentfolder) '/' num2str(length(showfold)) ',' showfold{currentfolder} ', event ' num2str(currentevent) '. Dur = ' ...
                    num2str(eventlengths{currentfolder}(currentevent)*dsrates(currentfolder)/reducedfSamps(currentfolder)) ' s, Q = ' ...
                    num2str(events{currentfolder}.quality(currentevent)) ', S = ' num2str(events{currentfolder}.synthesis(currentevent)) ', Cat = ' num2str(events{currentfolder}.category(currentevent)) '.'];
            title(titlename,'fontsize',12, 'color', qualitycolors(events{currentfolder}.quality(currentevent) + 2, :));
            %These cases set qualities, save, and reprint the title.
        case double('V')
            events{currentfolder}.quality(currentevent) = 0;
            event = events{currentfolder};
            save([folders{currentfolder} filesep 'event.mat'], 'event');
            clear event
            titlename = ['F:' num2str(currentfolder) '/' num2str(length(showfold)) ',' showfold{currentfolder} ', event ' num2str(currentevent) '. Dur = ' ...
                num2str(eventlengths{currentfolder}(currentevent)*dsrates(currentfolder)/reducedfSamps(currentfolder)) ' s, Q = ' ...
                num2str(events{currentfolder}.quality(currentevent)) ', S = ' num2str(events{currentfolder}.synthesis(currentevent)) ', Cat = ' num2str(events{currentfolder}.category(currentevent)) '.'];
            title(titlename,'fontsize',12, 'color', qualitycolors(events{currentfolder}.quality(currentevent) + 2, :));
        case double('C')
            events{currentfolder}.quality(currentevent) = 1;
            event = events{currentfolder};
            save([folders{currentfolder} filesep 'event.mat'], 'event');
            clear event
            titlename = ['F:' num2str(currentfolder) '/' num2str(length(showfold)) ',' showfold{currentfolder} ', event ' num2str(currentevent) '. Dur = ' ...
                num2str(eventlengths{currentfolder}(currentevent)*dsrates(currentfolder)/reducedfSamps(currentfolder)) ' s, Q = ' ...
                num2str(events{currentfolder}.quality(currentevent)) ', S = ' num2str(events{currentfolder}.synthesis(currentevent)) ', Cat = ' num2str(events{currentfolder}.category(currentevent)) '.'];
            title(titlename,'fontsize',12, 'color', qualitycolors(events{currentfolder}.quality(currentevent) + 2, :));
        case double('X')
            events{currentfolder}.quality(currentevent) = 2;
            event = events{currentfolder};
            save([folders{currentfolder} filesep 'event.mat'], 'event');
            clear event
            titlename = ['F:' num2str(currentfolder) '/' num2str(length(showfold)) ',' showfold{currentfolder} ', event ' num2str(currentevent) '. Dur = ' ...
                num2str(eventlengths{currentfolder}(currentevent)*dsrates(currentfolder)/reducedfSamps(currentfolder)) ' s, Q = ' ...
                num2str(events{currentfolder}.quality(currentevent)) ', S = ' num2str(events{currentfolder}.synthesis(currentevent)) ', Cat = ' num2str(events{currentfolder}.category(currentevent)) '.'];
            title(titlename,'fontsize',12, 'color', qualitycolors(events{currentfolder}.quality(currentevent) + 2, :))
        case double('Z')
            events{currentfolder}.quality(currentevent) = 3;
            event = events{currentfolder};
            save([folders{currentfolder} filesep 'event.mat'], 'event');
            clear event
            titlename = ['F:' num2str(currentfolder) '/' num2str(length(showfold)) ',' showfold{currentfolder} ', event ' num2str(currentevent) '. Dur = ' ...
                num2str(eventlengths{currentfolder}(currentevent)*dsrates(currentfolder)/reducedfSamps(currentfolder)) ' s, Q = ' ...
                num2str(events{currentfolder}.quality(currentevent)) ', S = ' num2str(events{currentfolder}.synthesis(currentevent)) ', Cat = ' num2str(events{currentfolder}.category(currentevent)) '.'];
            title(titlename,'fontsize',12, 'color', qualitycolors(events{currentfolder}.quality(currentevent) + 2, :))
            %Close the figure and end the program
        case double('N')
            if currentfolder == length(folders);
                currentfolder = 1;
                currentevent = 1;
                newplot = 1;
            else
                currentfolder = currentfolder + 1;
                currentevent = 1;
                newplot = 1;
            end
        case double('P')
            if currentfolder == 1
                currentfolder = length(folders);
                currentevent = 1;
                newplot = 1;
            else
                currentfolder = currentfolder - 1;
                currentevent = 1;
                newplot = 1;
            end
        case double('T')
            %classifying with tags
            title('Tap #1-9 to add a classifaction tag')
            ww = 0;
            while ww == 0
                ww = waitforbuttonpress;
            end
            inputt = double(upper(fig.CurrentCharacter));
            if ~(isstr(inputt)||isscalar(inputt))
                inputt = -100;
            else
                category = inputt-48;
            end
            if inputt <0
                disp('please choose #1-9')
                continue
            end
            events{currentfolder}.category(currentevent) = category;
            titlename = ['F:' num2str(currentfolder) '/' num2str(length(showfold)) ',' showfold{currentfolder} ', event ' num2str(currentevent) '. Dur = ' ...
                num2str(eventlengths{currentfolder}(currentevent)*dsrates(currentfolder)/reducedfSamps(currentfolder)) ' s, Q = ' ...
                num2str(events{currentfolder}.quality(currentevent)) ', S = ' num2str(events{currentfolder}.synthesis(currentevent)) ', Cat = ' num2str(events{currentfolder}.category(currentevent)) '.'];
            title(titlename,'fontsize',12, 'color', qualitycolors(events{currentfolder}.quality(currentevent) + 2, :))
            event = events{currentfolder};
            save([folders{currentfolder} filesep 'event.mat'], 'event');
        case double('F')
            %FastForward
            title('Tap  Z,X,C to FastForward to next Good Event of at least 3 2 or 1, or  #1-9 to see the next event classified as that # ')
            ww = 0;
            while ww == 0
                ww = waitforbuttonpress;
            end
            inputt = double(upper(fig.CurrentCharacter));
            if ~(isstr(inputt)||isscalar(inputt))
                inputt = -100 ;
            else
                nqual = 0;
                category = 0;
                if inputt==double('V')
                    nqual = 0;
                elseif inputt==double('C')
                    nqual = 1;
                elseif inputt==double('X')
                    nqual = 2;
                elseif inputt==double('Z')
                    nqual = 3;
                elseif inputt==double('B')
                    nqual = -1;
                elseif (inputt>=49&&inputt<=57)
                    category = inputt-48;
                end
                if nqual==0 && category==0;
                    disp('Not moving on to the next 0-marked event, dude');
                    continue
                end
            end
            [nqual category]
            
            
            ii = 1;
            % ii is for the purpose of preventing the users from
            % getting stuck in an infinite while loop if no good events
            % are found
            currentevent = currentevent + 1;
            if currentevent > length(events{currentfolder}.eventNum)
                currentfolder = currentfolder + 1;
                currentevent = 1;
                
                if currentfolder > length(folders)
                    disp('looping around');
                    currentfolder = 1;
                end
                
            end
            if nqual == -1;
                while (events{currentfolder}.quality(currentevent)>nqual)
                    currentevent = currentevent + 1;
                    if currentevent > length(events{currentfolder}.eventNum)
                        currentfolder = currentfolder + 1;
                        currentevent = 1;
                        ii = ii + 1;
                        if currentfolder > length(folders)
                            currentfolder = 1;
                        end
                        
                    end
                end
            else
                
                while ((category==0&& events{currentfolder}.quality(currentevent) <nqual)|| (nqual==0&& events{currentfolder}.category(currentevent) ~=category)) && ii <= length(folders)
                    
                    currentevent = currentevent + 1;
                    if currentevent > length(events{currentfolder}.eventNum)
                        currentfolder = currentfolder + 1;
                        currentevent = 1;
                        ii = ii + 1;
                        if currentfolder > length(folders)
                            currentfolder = 1;
                        end
                        
                    end
                    
                end
            end
            nqual=0;
            category=0;
            newplot = 1;
            %END FF HERE
        case double('R')
            title('Tap  Z,X,C to Rewind to previous Good Event of at least 3 2 or 1, or  #1-9 to see the next event classified as that # ')
            ww = 0;
            while ww == 0
                ww = waitforbuttonpress;
            end
            
            inputt = double(upper(fig.CurrentCharacter));
            if ~(isstr(inputt)||isscalar(inputt))
                inputt = -100 ;
            else
                nqual = 0;
                category = 0;
                if inputt==double('V')
                    nqual = 0;
                elseif inputt==double('C')
                    nqual = 1;
                elseif inputt==double('X')
                    nqual = 2;
                elseif inputt==double('Z')
                    nqual = 3;
                elseif (inputt>=49&&inputt<=57)
                    category = inputt-48;
                end
                if nqual==0 && category==0;
                    disp('Not moving on to the previous 0-marked event, dude');
                    continue
                end
            end
            
            ii = 1;
            % ii is for the purpose of preventing the users from
            % getting stuck in an infinite while loop if no good events
            % are found
            currentevent = currentevent - 1;
            if currentevent < 1
                currentfolder = currentfolder -1 ;
                if currentfolder < 1
                    currentfolder = length(folders);
                end
                currentevent = length(events{currentfolder}.eventNum);
            end
            
            while ((category==0&& events{currentfolder}.quality(currentevent) <nqual)|| (nqual==0&& events{currentfolder}.category(currentevent) ~=category)) && ii <= length(folders)
                
                currentevent = currentevent - 1;
                if currentevent < 1
                    currentfolder = currentfolder - 1;
                    ii = ii + 1;
                    if currentfolder < 1
                        currentfolder = length(folders);
                    end
                    currentevent = length(events{currentfolder}.eventNum);
                end
                
            end
            nqual=0;
            category=0;
            newplot = 1;
            
        case double('S')
            %Splitting events
            title('Running Multi-Event Splitter')
            pause(.5)
            title('READ CAREFULLY')
            pause(1)
            title('THIS CANNOT BE UNDONE')
            pause(1)
            title('HOLD Alt and click a point at the beginning and end of every event,unclick the datacursor on top and hit S again')
            dcm_obj = datacursormode(fig);
            set(dcm_obj,'DisplayStyle','datatip',...
                'SnapToDataVertex','off','Enable','on')
            
            oeStart = events{currentfolder}.eventStartNdx(currentevent);
            oeEnd = events{currentfolder}.eventEndNdx(currentevent);
            ww = 0;
            while ww == 0
                ww = waitforbuttonpress;
            end
            if double(upper(fig.CurrentCharacter)) == double('S')
                c_info = getCursorInfo(dcm_obj);
                if mod(length(c_info),2)~=0
                    disp('Select an even number of points, bozo')
                    continue
                end
                
                
                pointvector = [];
                for splitpoints = 1:length(c_info)
                    pointvector(end+1) = c_info(splitpoints).Position(1);
                end
                
                
                pointvector = sort(pointvector);
                if oeStart > floor(pointvector(1)*reducedfSamps(currentfolder)) || oeEnd < floor(pointvector(end)*reducedfSamps(currentfolder))
                    disp('Your points must be inbetween or ON the lines')
                    continue
                end
                fig;hold on;
                for pp = 1:2:length(pointvector)
                    p = patch([pointvector(pp) pointvector(pp+1) pointvector(pp+1) pointvector(pp)],[0 0 events{currentfolder}.localIOS(1) events{currentfolder}.localIOS(1)],'green','FaceAlpha',.3);
                end
                
                title('Are these the events you wanted? (Y/N)')
                ww = 0;
                while ww==0;
                    ww=waitforbuttonpress;
                end
                
                if double(upper(fig.CurrentCharacter)) == double('Y')
                    
                    events{currentfolder}= multieventSplitter(folders(currentfolder),pointvector);
                    
                    close(fig);
                    
                    fprintf(repmat('\b', 1, length(msg)));
                    msg = ['Loading and downsampling folder ' num2str(currentfolder) '. Please wait.'];
                    fprintf(msg)
                    
                    try
                        load([folders{currentfolder} filesep 'event.mat']);
                        load([folders{currentfolder} filesep 'reduced.mat']);
                        load([folders{currentfolder} filesep 'meta.mat']);
                        if isac, load([folders{currentfolder} filesep 'oeJava.mat']); end
                    catch
                        event.eventNum = [];
                    end
                    if isempty(event.eventNum)
                        folders(currentfolder) = [];
                        dsrates(currentfolder) = [];
                        dsdatas(currentfolder) = [];
                        ds_eventStartNdxs(currentfolder) = [];
                        ds_eventEndNdxs(currentfolder) = [];
                        eventlengths(currentfolder) = [];
                        events(currentfolder) = [];
                        IOSs(currentfolder) = [];
                        reducedfSamps(currentfolder) = [];
                        continue
                    end
                    %Find the downsampling frequency
                    if isfield(meta, 'acfrequency')
                        dsrates(currentfolder) = round(reduced.fSamp / meta.acfrequency);
                    elseif ~userDownsample
                        dsrates(currentfolder) = reduced.fSamp/dcdsfreq;
                    else
                        dsrates(currentfolder) = dsr; 
                    end

                    %Get and downsample the data. Re-index start and ends.
                    dsdatas{currentfolder} = downsampleinmatlab(reduced.data, dsrates(currentfolder));
                    ds_eventStartNdxs{currentfolder} = round(event.eventStartNdx/dsrates(currentfolder));
                    ds_eventEndNdxs{currentfolder} = round(event.eventEndNdx/dsrates(currentfolder));
                    eventlengths{currentfolder} = ds_eventEndNdxs{currentfolder}-ds_eventStartNdxs{currentfolder};
                    events{currentfolder} = event;
                    if isac
                        IOSs{currentfolder} = setIOS*ones(1, length(event.eventNum));
                    else
                        IOSs{currentfolder} = event.localIOS;
                    end
                    
                    reducedfSamps(currentfolder) = reduced.fSamp;
                    
                    fig = figure('Position', [100, 100, 1400, 700]);
                    clf, hold on
                    plotix = max(1, ds_eventStartNdxs{currentfolder}(currentevent)-round(eventlengths{currentfolder}(currentevent)/20)):min(length(dsdatas{currentfolder}), ds_eventEndNdxs{currentfolder}(currentevent) + round(eventlengths{currentfolder}(currentevent)/20));
                    plot( plotix * dsrates(currentfolder) / reducedfSamps(currentfolder), dsdatas{currentfolder}(plotix) )
                    plot([plotix(1), plotix(end)] * dsrates(currentfolder) / reducedfSamps(currentfolder), IOSs{currentfolder}(currentevent)*[1 1], '--r')
                    axis([plotix(1) * dsrates(currentfolder) / reducedfSamps(currentfolder), plotix(end) * dsrates(currentfolder) / reducedfSamps(currentfolder), 0, IOSs{currentfolder}(currentevent)*1.15]);
                    title('Split Complete')
                    newplot = 0;
                    
                    
                else
                    title(titlename)
                    
                    continue
                end
                %This else statement is if the ACparam variable
                %doesn't exist
                
                
                % Event Splitter ends here
            end
        case double('M')
            %Merging events
            %                 title('Are you sure you want to merge this event with the next one? If so, press ''M'' again. Otherwise, press another key to continue.')
            %                 ww = 0;
            %                 while ww == 0
            %                     ww = waitforbuttonpress;
            %                 end
            
            if currentevent == length(events{currentfolder}.eventNum)
                title('The event you are trying to merge is the last in this folder and will not work press any button OTHER than M')
                ww = 0;
                while ww == 0
                    ww = waitforbuttonpress;
                end
                
            else
                title('Are you sure you want to merge this event with the next one? If so, press ''M'' again. Otherwise, press another key to continue.')
                ww = 0;
                while ww == 0
                    ww = waitforbuttonpress;
                end
                if double(upper(fig.CurrentCharacter)) == double('M')
                    nextevent = currentevent+1;
                    events{currentfolder} = mergeEvents(folders(currentfolder),currentevent,nextevent,isac);
                    close(fig);
                    
                    
                    % resampling starts here
                    
                    fprintf(repmat('\b', 1, length(msg)));
                    msg = ['Loading and downsampling folder ' num2str(currentfolder) '. Please wait.'];
                    fprintf(msg)
                    
                    try
                        load([folders{currentfolder} filesep 'event.mat']);
                        load([folders{currentfolder} filesep 'reduced.mat']);
                        load([folders{currentfolder} filesep 'meta.mat']);
                        if isac, load([folders{currentfolder} filesep 'oeJava.mat']); end
                    catch
                        event.eventNum = [];
                    end
                    if isempty(event.eventNum)
                        folders(currentfolder) = [];
                        dsrates(currentfolder) = [];
                        dsdatas(currentfolder) = [];
                        ds_eventStartNdxs(currentfolder) = [];
                        ds_eventEndNdxs(currentfolder) = [];
                        eventlengths(currentfolder) = [];
                        events(currentfolder) = [];
                        IOSs(currentfolder) = [];
                        reducedfSamps(currentfolder) = [];
                        continue
                    end
                    %Find the downsampling frequency
                    if isfield(meta, 'acfrequency')
                        dsrates(currentfolder) = round(reduced.fSamp / meta.acfrequency);
                    elseif ~userDownsample
                        dsrates(currentfolder) = reduced.fSamp/dcdsfreq;
                    else
                        dsrates(currentfolder) = dsr;
                    end
                        %                     else
%                         dsrates(currentfolder) = reduced.fSamp/dcdsfreq;
%                     end
                    
                    %Get and downsample the data. Re-index start and ends.
                    dsdatas{currentfolder} = downsampleinmatlab(reduced.data, dsrates(currentfolder));
                    ds_eventStartNdxs{currentfolder} = round(event.eventStartNdx/dsrates(currentfolder));
                    ds_eventEndNdxs{currentfolder} = round(event.eventEndNdx/dsrates(currentfolder));
                    eventlengths{currentfolder} = ds_eventEndNdxs{currentfolder}-ds_eventStartNdxs{currentfolder};
                    events{currentfolder} = event;
                    if isac
                        IOSs{currentfolder} = setIOS*ones(1, length(event.eventNum));
                    else
                        IOSs{currentfolder} = event.localIOS;
                    end
                    
                    reducedfSamps(currentfolder) = reduced.fSamp;
                    
                    fig = figure('Position', [100, 100, 1400, 700]);
                    clf, hold on
                    plotix = max(1, ds_eventStartNdxs{currentfolder}(currentevent)-round(eventlengths{currentfolder}(currentevent)/20)):min(length(dsdatas{currentfolder}), ds_eventEndNdxs{currentfolder}(currentevent) + round(eventlengths{currentfolder}(currentevent)/20));
                    plot( plotix * dsrates(currentfolder) / reducedfSamps(currentfolder), dsdatas{currentfolder}(plotix) )
                    plot([plotix(1), plotix(end)] * dsrates(currentfolder) / reducedfSamps(currentfolder), IOSs{currentfolder}(currentevent)*[1 1], '--r')
                    axis([plotix(1) * dsrates(currentfolder) / reducedfSamps(currentfolder), plotix(end) * dsrates(currentfolder) / reducedfSamps(currentfolder), 0, IOSs{currentfolder}(currentevent)*1.15]);
                    title('Merge Complete')
                    newplot = 0;
                    
                    
                else
                    continue
                end
                
                % Merge Events Ends HERE
            end
            
        case double('Q')
            title('Are you sure you want to close? Q again to close')
            ww = 0;
            while ww == 0
                ww = waitforbuttonpress;
            end
            if double(upper(fig.CurrentCharacter)) == double('Q')
                close(fig)
                return;
            else
                continue
            end
        case 27 %escape key
            
            
            close(fig)
            return;
        otherwise
            'I do not understand you, Daniel-san'
            
    end
    
    %If we have gone past the end or beginning of a folder, go to the
    %next one.
    if currentevent < 1
        if currentfolder == 1
            currentfolder = length(folders);
        else
            currentfolder = currentfolder-1;
        end
        currentevent = length(events{currentfolder}.eventNum);
    elseif currentevent > length(events{currentfolder}.eventNum)
        if currentfolder == length(folders);
            currentfolder = 1;
        else
            currentfolder = currentfolder+1;
        end
        currentevent = 1;
    end
    
end

end


end

# Main script to run to run LickTrain_v2 behavior

import time
import json
import os
import sys
import os
import numpy as np, pandas
import my
import time
import curses
import matplotlib.pyplot as plt
import ArduFSM
import ArduFSM.chat
import ArduFSM.plot
from ArduFSM import TrialSpeak, TrialMatrix
from ArduFSM import trial_setter_ui
from ArduFSM import Scheduler
from ArduFSM import trial_setter
from ArduFSM import mainloop
import ParamsTable

def get_trial_types(name, directory='~/dev/ArduFSM/stim_sets'):
    """Loads and returns the trial types file"""
    
    filename = os.path.join(os.path.expanduser(directory), name)
    try:
        trial_types = pandas.read_csv(filename)
    except IOError:
        raise ValueError("cannot find trial type file %s" % name)
    return trial_types

# Load the parameters file
with file('parameters.json') as fi:
    runner_params = json.load(fi)

# Check the serial port exists
if not os.path.exists(runner_params['serial_port']):
    raise OSError("serial port %s does not exist" % 
        runner_params['serial_port'])


## Determine how to set up the webcam
# Get controls from runner_params
webcam_controls = {}
for webcam_param in ['brightness', 'gain', 'exposure']:
    rp_key = 'video_' + webcam_param
    if rp_key in runner_params:
        webcam_controls[webcam_param] = runner_params[rp_key]

# Determine whether we can show it
video_device = runner_params.get('video_device', None)
if video_device is None:
    SHOW_WEBCAM = False
else:
    SHOW_WEBCAM = True


## Only show the IR_plot if use_ir_detector
SHOW_IR_PLOT = runner_params.get('use_ir_detector', False)

# sensor plot
SHOW_SENSOR_PLOT = False


## Various window positions
video_window_position = runner_params.get('video_window_position', None)
gui_window_position = runner_params.get('gui_window_position', None)
window_position_IR_detector = runner_params.get(
    'window_position_IR_detector', None)
    
## Set up params_table
# First we load the table of protocol-specific parameters that is used by the UI
# Then we assign a few that were set by the runner
params_table = ParamsTable.get_params_table()
params_table.loc['RD_L', 'init_val'] = runner_params['l_reward_duration']
params_table.loc['RD_R', 'init_val'] = runner_params['r_reward_duration']
params_table.loc['MRT', 'init_val'] = runner_params['MRT']
if runner_params['use_ir_detector']:
    params_table.loc['TOUT', 'init_val'] = runner_params['l_ir_detector_thresh']    
    params_table.loc['RELT', 'init_val'] = runner_params['r_ir_detector_thresh']   

# Set the current-value to be equal to the init_val
params_table['current-value'] = params_table['init_val'].copy()


## Load the specified trial types
trial_types_name = 'trial_types_licktrain'
trial_types = get_trial_types(trial_types_name)


## User interaction
session_results = {}
# Get weight
session_results['mouse_mass'] = \
    raw_input("Enter mass of %s: " % runner_params['mouse'])
raw_input("Fill water reservoirs and press Enter to start")


## Initialize the scheduler
scheduler = Scheduler.ForcedAlternationLickTrain(trial_types=trial_types)

## Create Chatter
logfilename = None # autodate
chatter = ArduFSM.chat.Chatter(to_user=logfilename, to_user_dir='./logfiles',
    baud_rate=115200, serial_timeout=.1, 
    serial_port=runner_params['serial_port'])
logfilename = chatter.ofi.name


## Reset video filename
date_s = os.path.split(logfilename)[1].split('.')[1]
video_filename = os.path.join(os.path.expanduser('~/Videos'), 
    '%s-%s.mkv' % (runner_params['box'], date_s))
video_filename = None

## Trial setter
ts_obj = trial_setter.TrialSetter(chatter=chatter, 
    params_table=params_table,
    scheduler=scheduler)

## Initialize UI
RUN_UI = True
RUN_GUI = True
ECHO_TO_STDOUT = not RUN_UI
if RUN_UI:
    ui = trial_setter_ui.UI(timeout=100, chatter=chatter, 
        logfilename=logfilename,
        ts_obj=ts_obj)

    try:
        ui.start()

    except curses.error as err:
        raise Exception(
            "UI error. Most likely the window is, or was, too small.\n"
            "Quit Python, type resizewin to set window to 80x23, and restart.")

    except:
        print "error encountered when starting UI"
        raise
    
    finally:
        ui.close()


## Main loop
final_message = None
try:
    ## Initialize webcam
    if SHOW_WEBCAM:
        window_title = runner_params['box'] + '_licktrain'
        try:
            wc = my.video.WebcamController(device=video_device, 
                output_filename=video_filename,
                window_title=window_title,
                image_controls=webcam_controls,)
            wc.start()
        except IOError:
            print "cannot find webcam at port", video_device
            wc = None
            SHOW_WEBCAM = False
    else:
        wc = None
    
    ## Initialize GUI
    if RUN_GUI:
        plotter = ArduFSM.plot.PlotterWithServoThrow(trial_types)
        plotter.init_handles()
        if True:# rigname in ['L0', 'B1', 'B2', 'B3', 'B4',]:
            # for backend tk
            #~ plotter.graphics_handles['f'].canvas.manager.window.wm_geometry("+700+0")
            plotter.graphics_handles['f'].canvas.manager.window.wm_geometry(
                "+%d+%d" % (gui_window_position[0], gui_window_position[1]))
            plt.show()
            plt.draw()
        else:
            # for backend gtk
            plotter.graphics_handles['f'].canvas.manager.window.move(
                gui_window_position[0], gui_window_position[1])
        
        last_updated_trial = 0
    
    # Move the webcam window once it appears
    if SHOW_WEBCAM:
        cmd = 'xdotool search --name %s windowmove %d %d' % (
            window_title, video_window_position[0], video_window_position[1])
        while os.system(cmd) != 0:
            # Should test here if it's been too long and then give up
            print "Waiting for webcam window"
            time.sleep(.5)
    
    while True:
        ## Chat updates
        # Update chatter
        chatter.update(echo_to_stdout=ECHO_TO_STDOUT)
        
        # Read lines and split by trial
        # Could we skip this step if chatter reports no new device lines?
        logfile_lines = TrialSpeak.read_lines_from_file(logfilename)
        splines = TrialSpeak.split_by_trial(logfile_lines)

        # Run the trial setting logic
        # This try/except is no good because it conflates actual
        # ValueError like sending a zero
        #~ try:
        translated_trial_matrix = ts_obj.update(splines, logfile_lines)
        #~ except ValueError:
            #~ raise ValueError("cannot get any lines; try reuploading protocol")
        
        ## Update UI
        if RUN_UI:
            ui.update_data(logfile_lines=logfile_lines)
            ui.get_and_handle_keypress()

        ## Update GUI
        # Put this in it's own try/except to catch plotting bugs
        if RUN_GUI:
            if last_updated_trial < len(translated_trial_matrix):
                # update plot
                plotter.update(logfilename)     
                last_updated_trial = len(translated_trial_matrix)
                
                # don't understand why these need to be here
                plt.show()
                plt.draw()


except KeyboardInterrupt:
    print "Keyboard interrupt received"

except trial_setter_ui.QuitException as qe:
    final_message = qe.message
    
    # Get weight
    session_results['l_volume'] = raw_input("Enter L water volume: ")
    session_results['r_volume'] = raw_input("Enter R water volume: ")
    session_results['final_pipe'] = raw_input("Enter final pipe position: ")
    with file(os.path.join(os.path.split(logfilename)[0], 'results'), 'w') as fi:
        json.dump(session_results, fi, indent=4)

except curses.error as err:
    raise Exception(
        "UI error. Most likely the window is, or was, too small.\n"
        "Quit Python, type resizewin to set window to 80x23, and restart.")

except:
    raise

finally:
    if SHOW_WEBCAM:
        wc.stop()
        wc.cleanup()
    chatter.close()
    print "chatter closed"
    
    if RUN_UI:
        ui.close()
        print "UI closed"
    
    if RUN_GUI:
        pass
        #~ plt.close(plotter.graphics_handles['f'])
        #~ print "GUI closed"
    
    if final_message is not None:
        print final_message
    



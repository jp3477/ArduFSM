# Main script to run to run TwoChoice_v2 behavior
# Timings: set 'serial_timeout' in chatter, and 'timeout' in UI, to be low
# enough that the response is quick, but not so low that it takes up all the
# CPU power.
# Right now, it does this on each loop
# * Update chatter (timeout)
# * Update UI (timeout)
# * do other things, like reading logfile and setting next trial
# So, if the timeouts are too low, it spends a lot more time reading the
# logfile and there is more overhead overall.

import sys
import os
import numpy as np, pandas
import my
import time
import curses
import matplotlib.pyplot as plt

# Ardu imports. Because this is an example script that will be run in another
# directory, don't assume we can import TrialSpeak et al directly
import ArduFSM
from ArduFSM import TrialSpeak, TrialMatrix
from ArduFSM import trial_setter_ui
from ArduFSM import Scheduler
from ArduFSM import trial_setter
from ArduFSM import mainloop


## Find out what rig we're in using the current directory
this_dir_name = os.getcwd()
rigname = os.path.split(this_dir_name)[1]
serial_port = mainloop.get_serial_port(rigname)
#~ serial_port = '/dev/ttyACM0'

if not os.path.exists(serial_port):
    raise OSError("serial port %s does not exist" % serial_port)

## Get params
params_table = mainloop.get_params_table()
params_table = mainloop.assign_rig_specific_params(rigname, params_table)
params_table['current-value'] = params_table['init_val'].copy()

## Upload
if raw_input('Reupload protocol [y/N]? ').upper() == 'Y':
    if rigname in ['L0']:
        protocol_name = 'TwoChoice'
    else:
        protocol_name = 'TwoChoice_%s' % rigname
    os.system('arduino --board arduino:avr:uno --port %s \
        --pref sketchbook.path=/home/mouse/dev/ArduFSM \
        --upload ~/dev/ArduFSM/%s/%s.ino' % (
        serial_port, protocol_name, protocol_name))
    
    # Should look for programmer is not responding in output and warn user
    # to plug/unplug arduino

## Set parameters
# Get a rig parameter
if rigname in ['L0', 'L5', 'L6']:
    reverse_srvpos = True
else:
    reverse_srvpos = False

# Set the trial types and scheduler based on the mouse name
mouse_parameters_df = pandas.DataFrame.from_records([
    ('default', 'trial_types_2srvpos_80pd', Scheduler.Auto,),
    ('KM38', 'trial_types_3srvpos_80pd', Scheduler.Auto,),
    ('KM52', 'trial_types_2srvpos_80pd', Scheduler.ForcedAlternation,),
    ('KF60', 'trial_types_CCL_1srvpos', Scheduler.ForcedAlternation,),
    ('KF61', 'trial_types_1srvpos', Scheduler.ForcedAlternation,),
    ('KF62', 'trial_types_CCL_1srvpos', Scheduler.ForcedAlternation,),
    ('KM63', 'trial_types_CCL_1srvpos', Scheduler.ForcedAlternation,),
    ('KM64', 'trial_types_CCL_1srvpos', Scheduler.ForcedAlternation,),
    ('KM65', 'trial_types_CCL_1srvpos', Scheduler.ForcedAlternation,),
    ('KF69', 'trial_types_gng_1srvpos', Scheduler.RandomStim,),
    ('KF70', 'trial_types_gng_1srvpos', Scheduler.RandomStim,),
    ('KF71', 'trial_types_gng_1srvpos', Scheduler.RandomStim,),
    ], columns=('mouse', 'trial_types', 'scheduler'),
    ).set_index('mouse')

# Get the mouse name
while True:
    # Get the mosue name (default is blank, continue if not in index)
    mouse_name = raw_input("Enter mouse name: ")
    mouse_name = mouse_name.upper().strip()
    if mouse_name == '':
        mouse_name = 'default'
    if mouse_name not in mouse_parameters_df.index:
        continue
    
    # Get the trial types (optionally reversing by rig)
    trial_types_name = mouse_parameters_df.loc[mouse_name, 'trial_types']
    if reverse_srvpos:
        trial_types_name = trial_types_name + '_r'
    
    # Get the scheduler
    scheduler_obj = mouse_parameters_df.loc[mouse_name, 'scheduler']
    break

## Now actually load the trial type
trial_types = mainloop.get_trial_types(trial_types_name)

## Initialize the scheduler
# Do all scheduler objects accept reverse_srvpos?
scheduler = scheduler_obj(trial_types=trial_types, reverse_srvpos=reverse_srvpos)

## Create Chatter
logfilename = 'out.log'
logfilename = None # autodate
chatter = ArduFSM.chat.Chatter(to_user=logfilename, to_user_dir='./logfiles',
    baud_rate=115200, serial_timeout=.1, serial_port=serial_port)
logfilename = chatter.ofi.name

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
    ## Initialize GUI
    if RUN_GUI:
        plotter = ArduFSM.plot.PlotterWithServoThrow(trial_types)
        plotter.init_handles()
        if rigname == 'L1':
            plotter.graphics_handles['f'].canvas.manager.window.move(500, 0)
        elif rigname == 'L2':
            plotter.graphics_handles['f'].canvas.manager.window.move(500, 400)
        elif rigname == 'L3':
            plotter.graphics_handles['f'].canvas.manager.window.move(500, 800)
        elif rigname == 'L5':
            plotter.graphics_handles['f'].canvas.manager.window.move(500, 1000)
        elif rigname == 'L6':
            plotter.graphics_handles['f'].canvas.manager.window.move(500, 1400)
            
        elif rigname == 'L0':
            plotter.graphics_handles['f'].canvas.manager.window.wm_geometry("+700+0")
        
        last_updated_trial = 0
    
    while True:
        ## Chat updates
        # Update chatter
        chatter.update(echo_to_stdout=ECHO_TO_STDOUT)
        
        # Read lines and split by trial
        # Could we skip this step if chatter reports no new device lines?
        logfile_lines = TrialSpeak.read_lines_from_file(logfilename)
        splines = TrialSpeak.split_by_trial(logfile_lines)

        # Run the trial setting logic
        try:
            translated_trial_matrix = ts_obj.update(splines, logfile_lines)
        except ValueError:
            raise ValueError("cannot get any lines; try reuploading protocol")
        
        ## Meta-scheduler
        # Not sure how to handle this yet. Probably should be an object
        # ts_obj.meta_scheduler that can change ts_obj.scheduler, or a method
        # meta_scheduler(trial_matrix) that returns the new scheduler
        # Actually, probably makes the most sense to have each meta-scheduler
        # just be a scheduler called "auto" or something.
        if len(translated_trial_matrix) > 8 and ts_obj.scheduler.name == 'session starter':
            new_scheduler = Scheduler.ForcedAlternation(trial_types=trial_types)
            ts_obj.scheduler = new_scheduler
        
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

except curses.error as err:
    raise Exception(
        "UI error. Most likely the window is, or was, too small.\n"
        "Quit Python, type resizewin to set window to 80x23, and restart.")

except:
    raise

finally:
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
    



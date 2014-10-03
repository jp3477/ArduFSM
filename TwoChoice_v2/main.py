# Test script for SimpleTrialRelease
import ArduFSM
import TrialSpeak, TrialMatrix
import numpy as np, pandas
import my
import time

logfilename = 'out.log'
chatter = ArduFSM.chat.Chatter(to_user=logfilename, baud_rate=115200, 
    serial_timeout=.1, serial_port='/dev/ttyACM0')

# The ones that are fixed at the beginning
initial_params = {
    'MRT': 3,
    'RWIN': 10000,
    }

# Define the possible types of trials here
# This should be loaded from disk, not written to disk.
trial_types = pandas.DataFrame.from_records([
    {'name':'CV-L-1150-050', 'srvpos':1150, 'stppos':50, 'rewside':'left',},
    {'name':'CC-R-1150-150', 'srvpos':1150, 'stppos':150, 'rewside':'right',},
    {'name':'CV-L-1175-050', 'srvpos':1175, 'stppos':50, 'rewside':'left',},
    {'name':'CC-R-1175-150', 'srvpos':1175, 'stppos':150, 'rewside':'right',},
    ])
trial_types.to_pickle('trial_types_2stppos')


def generate_trial_params(trial_matrix):
    """Given trial matrix so far, generate params for next"""
    res = {}
    
    if len(trial_matrix) == 0:
        # First trial, so pick at random from trial_types
        idx = trial_types.index[np.random.randint(0, len(trial_types))]
        res['RWSD'] = trial_types['rewside'][idx]
        res['STPPOS'] = trial_types['stppos'][idx]
        res['SRVPOS'] = trial_types['srvpos'][idx]
        res['ITI'] = np.random.randint(10000)
    
    else:    
        # Not the first trial
        # First check that the last trial hasn't been released
        assert trial_matrix['release_time'].isnull().irow(-1)
        
        # But that it has been responded
        assert not trial_matrix['choice'].isnull().irow(-1)
        
        # Set side to left by default, and otherwise forced alt
        if len(trial_matrix) < 2:
            res['RWSD'] = 'left'
        else:
            # Get last trial
            last_trial = trial_matrix.irow(-1)
            if last_trial['choice'] == last_trial['rewside']:
                res['RWSD'] = {'left': 'right', 'right':'left'}[last_trial['rewside']]
            else:
                res['RWSD'] = last_trial['rewside']
        
        # Use the forced side to choose from trial_types
        sub_trial_types = my.pick_rows(trial_types, rewside=res['RWSD'])
        assert len(sub_trial_types) > 0
        idx = sub_trial_types.index[np.random.randint(0, len(sub_trial_types))]
        
        res['STPPOS'] = trial_types['stppos'][idx]
        res['SRVPOS'] = trial_types['srvpos'][idx]
        res['ITI'] = np.random.randint(10000)
        
    # Untranslate the rewside
    # This should be done more consistently, eg, use real phrases above here
    # and only untranslate at this point.
    res['RWSD'] = {'left': 1, 'right': 2}[res['RWSD']]
    
    return res


def choose_params_send_and_release(translated_trial_matrix):
    """Choose params for next unreleased trial, send, and release."""
    params = generate_trial_params(translated_trial_matrix)

    # Set them
    for param_name, param_val in params.items():
        chatter.write_to_device(
            TrialSpeak.command_set_parameter(
                param_name, param_val))
        time.sleep(1.0)
    
    # Release
    chatter.write_to_device(TrialSpeak.command_release_trial())    

def is_current_trial_incomplete(translated_trial_matrix):
    if len(translated_trial_matrix) < 1:
        raise ValueError("no trials have begun")
    if 'choice' not in translated_trial_matrix.columns:
        raise ValueError("need translated matrix")
    
    return translated_trial_matrix['choice'].isnull().irow(-1)

## Main loop
initial_params_sent = False
last_released_trial = -1
try:
    while True:
        # Update chatter
        chatter.update(echo_to_stdout=True)
        
        # Check log
        splines = TrialSpeak.load_splines_from_file(logfilename)

        # Behavior depends on how much data has been received
        if len(splines) == 0:
            # No data received, or possibly munged data received.
            # Add some more error checks for this            
            continue
        if len(splines) == 1:
            # Some data has been received, so the Arduino has booted up.
            # Add an error check that it is speaking our language here.
            # But no trials have occurred yet (splines[0] is setup info).
            # Send initial params if they haven't already been sent
            if not initial_params_sent:
                # Send each initial param
                for param_name, param_val in initial_params.items():
                    cmd = TrialSpeak.command_set_parameter(param_name, param_val)           
                    chatter.write_to_device(cmd)
                    time.sleep(0.5)
                
                # Mark as sent
                initial_params_sent = True

        # Now we know that the Arduino has booted up and that the initial
        # params have been sent.
        # Construct trial_matrix
        trial_matrix = TrialMatrix.make_trials_info_from_splines(splines)
        current_trial = len(trial_matrix) - 1
        
        
        # Translate
        translated_trial_matrix = TrialSpeak.translate_trial_matrix(trial_matrix)

        # Was the last released trial the current one or the next one?
        if last_released_trial < current_trial:
            raise "unreleased trials have occurred, somehow"
            
        elif last_released_trial == current_trial:
            # The current trial has been released, or no trials have been released
            if current_trial == -1:
                # first trial has not even been released yet, nor begun
                choose_params_send_and_release(translated_trial_matrix)            
                last_released_trial = current_trial + 1
            elif is_current_trial_incomplete(translated_trial_matrix):
                # Current trial has been released but not completed
                pass
            else:
                # Current trial has been completed. Next trial needs to be released.
                choose_params_send_and_release(translated_trial_matrix)                
                last_released_trial = current_trial + 1            
        
        elif last_released_trial == current_trial + 1:
            # Next trial has been released, but has not yet begun
            pass
        
        else:
            raise "too many trials have been released, somehow"


## End cleanly upon keyboard interrupt signal
except KeyboardInterrupt:
    print "Keyboard interrupt received"
except:
    raise
finally:
    chatter.close()
    print "Closed."
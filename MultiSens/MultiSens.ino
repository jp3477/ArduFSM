/* OVERVIEW 160607:
 * This file is the main Arduino sketch for the ArduFSM protocol MultiSens. This 
 * protocol is used for presenting simultaneous multi-sensory stimuli. 
 * Arbitrary stimulus presentations can be paired with coterminous dispensation 
 * of a liquid reward (determined by the computer-side program), and licks during 
 * non-rewarded stimuli will result in a timeout error period.
 *  
 * REQUIREMENTS:
 * This sketch must be located in the MultiSens protocol directory within
 * a copy of the ArduFSM repository on the local computer's Arduino sketchbook
 * folder. In addition to this file, the MultiSens directory should contain
 * the following files:
 *  
 * 1. config.h
 * 2. config.cpp
 * 3. States.h
 * 4. States.cpp
 *  
 * In addition, the local computer's Arduino sketchbook library must contain 
 * the following libraries:
 *  
 * 1. chat, available at https://github.com/cxrodgers/ArduFSM/tree/master/libraries/chat
 * 2. devices, available at https://github.com/danieldkato/devices
 *  
 * This sketch is largely agnostic with respect to how the computer-side code is
 * implemented; the only requirements are that both programs specify the same
 * baud rate for the serial connection, and that the computer-side code send
 * certain specific messages comprised of byte arrays terminated by a newline
 * ('\n') character over a serial connection to the Arduino. The syntax and
 * semantics of these messages are described below.
 *  
 * DESCRIPTION:
 * Like all ArduFSM programs, this sketch, on every pass of the main loop, 
 * performs the following actions: 1) check for messages from the computer,
 * 2) check for licks, 3) performs state-dependent operations, and 4) if 
 * necessary, advances the current state. 
 *  
 * The protocol consits of 8 states: WAIT_TO_START_TRIAL, TRIAL_START, STIM_PERIOD,   
 * RESPONSE_WINDOW, REWARD, POST_REWARD_PAUSE, ERROR and INTER_TRIAL_INTERVAL.  
 * During WAIT_TO_START_TRIAL, the Arduino does nothing until it receives the
 * message "RELEASE_TRL\0\n" from the computer. It then advances to TRIAL_START,
 * when it prints the current trial parameters back to the computer. It then  
 * advances to STIM_PERIOD, during which it presents the stimuli. 
 * 
 * On rewarded trials, the reward valve will open some amount of time before 
 * the end of STIM_PERIOD. The state will then advance to RESPONSE_PERIOD, during 
 * which licks will cause the state to advance to REWARD, during which the reward
 * valve will open. This will be followed by a POST_REWARD_PAUSE, which will cycle
 * back to RESPONSE_WINDOW. As long as the mouse keeps licking, this cycle will
 * repeat until some maximum number of rewards is reached. If no licks are 
 * recorded during the response window, no further rewards are given, and the
 * trial is scored as a miss. 
 * 
 * On unrewarded trials, any licks during the STIM_PERIOD or RESPONSE_WINDOW
 * states will result in a false alarm outcome and cause the state to advance
 * to ERROR. If no licks are detected during either STIM_PERIOD or 
 * RESPONSE_WINDOW, then the trial is scored as a correct reject. 
 * 
 * In any case, after the trial is scored, the state will advance to
 * INTER_TRIAL_INTERVAL, during which it will report back the trial outcome,
 * and then to WAIT_TO_START_TRIAL, during which it will await the parameters
 * for the next trial and the "RELEASE_TRL\0" message to begin the next trial.
 * 
 * This sketch expects to receive trial parameters in messages with the syntax:
 * 
 * "SET <parameter abbreviation> <parameter value>\n"
 * 
 * where <parameters abbreviation> stands for some parameter abbreviation and
 * <parameter value> stands for the value of that parameter on the upcoming 
 * trial.
 * 
 * The semantics of the parameters abbreviations are as follows:
 * 
 * STPRIDX: function index for the stepper motor; used by an object 
 * representing the stepper motor to determine what actions to take during the 
 * stimulus period. 0 means do nothing, 1 means extend the stepper at the 
 * beginning of the trial. 
 * 
 * SPKRIDX: function index for the speaker. 0 means do nothing, 1 means 
 * play a white noise stimulus. Set to 0 by default on the Arduino. 
 * 
 * REW: whether or not the current trial will be rewarded. Set to 0 by default 
 * on the Arduino.
 * 
 * REW_DUR: the duration of any rewards given on the current trial. Set to 50 
 * by default on the Arduino.
 * 
 * IRI: inter-reward interval; the minimum amount of time that must elapse 
 * between rewards. Set to 500 by default on the Arduino. 
 * 
 * TO: timeout; the minimum amount of time between a false alarm response and 
 * the following trial. Set to 6000 by default on the Arduino.
 * 
 * ITI: inter-trial interval; minimum amount of time between trials [?]. Set to 
 * 3000 by default on the Arduino.
 * 
 * RWIN: response window duration; the maximum amount of time the mouse has to 
 * respond following the stimulus. Set to 45000 by default on the Arduino.
 * 
 * MRT: maximum number of rewards mouse can receive on a single trial. Set 
 * to 1 by default on the Arduino.
 * 
 * TOE: terminate on error; whether or not the trial will end immediately 
 * following a false alarm response. Set to 1 by default on the Arduino. 

  */ 

/* TODO
----
* Move the required states, like TRIAL_START and WAIT_FOR_NEXT_TRIAL,
  as well as all required variables like flag_start_trial, into TrialSpeak.cpp.
* move definitions of trial_params to header file, so can be auto-generated
* diagnostics: which state it is in on each call (or subset of calls)

Here are the things that the user should have to change for each protocol:
* Enum of states
* User-defined states in switch statement
* param_abbrevs, param_values, tpidx_*, N_TRIAL_PARAMS
*/
#include "chat.h"
//#include <Wire.h> // also for mpr121
#include <Stepper.h>
#include "TimedState.h"
#include "States.h"

// Make this true to generate random responses for debugging
#define FAKE_RESPONDER 0

extern char* param_abbrevs[N_TRIAL_PARAMS];
extern long param_values[N_TRIAL_PARAMS];
extern bool param_report_ET[N_TRIAL_PARAMS];
extern char* results_abbrevs[N_TRIAL_RESULTS];
extern long results_values[N_TRIAL_RESULTS];
extern long default_results_values[N_TRIAL_RESULTS];

//// Miscellaneous globals
// flag to remember whether we've received the start next trial signal
// currently being used in both setup() and loop() so it can't be staticked
bool flag_start_trial = 0;

TimedState ** states = getStates();

//// Declarations
int take_action(char *protocol_cmd, char *argument1, char *argument2);


//// User-defined variables, etc, go here
/// these should all be staticked into loop()
STATE_TYPE next_state; 

// touched monitor
boolean sticky_licking = 0;

/// not sure how to static these since they are needed by both loop and setup

//// Setup function
void setup()
{
  unsigned long time = millis();
  int status = 1;
  
  Serial.begin(115200);
  Serial.print(time);
  Serial.println(" DBG begin setup");
  
  // random number seed
  randomSeed(analogRead(3));
  
  //// Run communications until we've received all setup info
  // Later make this a new flag. For now wait for first trial release.
  while (!flag_start_trial)
  {
    status = communications(time);
    if (status != 0)
    {
      Serial.println("comm error in setup");
      delay(1000);
    }
  }
}



//// Loop function
void loop()
{ /* Called over and over again. On each call, the behavior is determined
     by the current state.
  */
  
  //// Variable declarations
  // get the current time as early as possible in this function
  unsigned long time = millis();

  // statics 
  // these are just "declared" here, they can be modified at the beginning
  // of each trial
  static STATE_TYPE current_state = WAIT_TO_START_TRIAL;

  // The next state, by default the same as the current state
  next_state = current_state;
    
  
  // misc
  int status = 1;
  
  //// User protocol variables
  boolean licking = 0;
  
  
  //// Run communications
  status = communications(time);
  
  
  //// User protocol code
  // could put other user-specified every_loop() stuff here
  
  // Poll touch inputs
  licking = checkLicks();
  
  // announce sticky
  if (licking != sticky_licking)
  {
    Serial.print(time);
    Serial.print(" LCK ");
    sticky_licking = licking;
  }  
  
  //// Begin state-dependent operations
  // Try to replace every case with a single function or object call
  // Ultimately this could be a dispatch table.
  // Also, eventually we'll probably want them to return next_state,
  // but currently it's generally passed by reference.
  switch (current_state)
  {
    //// Wait till the trial is released. Same for all protocols.
    case WAIT_TO_START_TRIAL:
      // Wait until we receive permission to continue  
      if (flag_start_trial)
      {
        // Announce that we have ended the trial and reset the flag
        Serial.print(time);
        Serial.println(" TRL_RELEASED");
        flag_start_trial = 0;
        
        // Proceed to next trial
        next_state = TRIAL_START;
      }
      break;

    //// TRIAL_START. Same for all protocols.
    case TRIAL_START:
    
      // Set up the trial based on received trial parameters
      Serial.print(time);
      Serial.println(" TRL_START");
      for(int i=0; i < N_TRIAL_PARAMS; i++)
      {
        if (param_report_ET[i]) 
        {
          // Buffered write would be nice here
          Serial.print(time);
          Serial.print(" TRLP ");
          Serial.print(param_abbrevs[i]);
          Serial.print(" ");
          Serial.println(param_values[i]);
        }
      }
    
      // Set up trial_results to defaults
      for(int i=0; i < N_TRIAL_RESULTS; i++)
      {
        results_values[i] = default_results_values[i];
      }      
      
      
      //// User-defined code goes here
      // declare the states. Here we're both updating the parameters
      // in case they've changed, and resetting all timers.
    
      next_state = STIM_PERIOD;
      break;

    case STIM_PERIOD:
      states[stidx_STIM_PERIOD]->run(time);
      break;
    
    case RESPONSE_WINDOW:
      if (FAKE_RESPONDER)
      {
        states[stidx_FAKE_RESPONSE_WINDOW]->update();
        states[stidx_FAKE_RESPONSE_WINDOW]->run(time);
      } 
      else 
      {
        states[stidx_RESPONSE_WINDOW]->update();
        states[stidx_RESPONSE_WINDOW]->run(time);
      }
      break;
    
    case REWARD:
      Serial.print(time);
      Serial.println(" EV R_L");
      state_reward(next_state);
      break;
    
    case POST_REWARD_PAUSE:
      states[stidx_POST_REWARD_PAUSE]->run(time);
      break;    
    
    case ERROR:
      
      states[stidx_ERROR]->run(time);
      break;

    case INTER_TRIAL_INTERVAL:

      // Announce trial_results
      states[stidx_INTER_TRIAL_INTERVAL]->run(time);
      break;
    
    // need an else here
  }
  
  
  //// Update the state variable
  if (next_state != current_state)
  {
      
    Serial.print(time);
    Serial.print(" ST_CHG ");
    Serial.print(current_state);
    Serial.print(" ");
    Serial.println(next_state);
    
    Serial.print(millis());
    Serial.print(" ST_CHG2 ");
    Serial.print(current_state);
    Serial.print(" ");
    Serial.println(next_state);
  }
  current_state = next_state;
  
  return;
}


//// Take protocol action based on user command (ie, setting variable)
int take_action(char *protocol_cmd, char *argument1, char *argument2)
{ /* Protocol action.
  
  Currently two possible actions:
    if protocol_cmd == 'SET':
      argument1 is the variable name. argument2 is the data.
    if protocol_cmd == 'ACT':
      argument1 is converted into a function based on a dispatch table.
        REWARD_L : reward the left valve
        REWARD_R : reward the right valve
        REWARD : reward the current valve

  This logic could be incorporated in TrialSpeak, but we would need to provide
  the abbreviation, full name, datatype, and optional handling logic for
  each possible variable. So it seems to make more sense here.
  
  Return values:
  0 - command parsed successfully
  2 - unimplemented protocol_cmd
  4 - unknown variable on SET command
  5 - data conversion error
  6 - unknown asynchronous action
  */
  int status;
  
  //~ Serial.print("DBG take_action ");
  //~ Serial.print(protocol_cmd);
  //~ Serial.print("-");
  //~ Serial.print(argument1);
  //~ Serial.print("-");
  //~ Serial.println(argument2);
  
  if (strncmp(protocol_cmd, "SET\0", 4) == 0)
  {
    // Find index into param_abbrevs
    int idx = -1;
    for (int i=0; i < N_TRIAL_PARAMS; i++)
    {
      if (strcmp(param_abbrevs[i], argument1) == 0)
      {
        idx = i;
        break;
      }
    }
    
    // Error if not found, otherwise set
    if (idx == -1)
    {
      Serial.print("ERR param not found ");
      Serial.println(argument1);
      return 4;
    }
    else
    {
      // Convert to int
      status = safe_int_convert(argument2, param_values[idx]);

      // Debug
      //~ Serial.print("DBG setting var ");
      //~ Serial.print(idx);
      //~ Serial.print(" to ");
      //~ Serial.println(argument2);

      // Error report
      if (status != 0)
      {
        Serial.println("ERR can't set var");
        return 5;
      }
    }
  }   

  else if (strncmp(protocol_cmd, "ACT\0", 4) == 0)
  {
    // Dispatch
    return 6;
  }      
  else
  {
    // unknown command
    return 2;
  }
  return 0;
}


int safe_int_convert(char *string_data, long &variable)
{ /* Check that string_data can be converted to long before setting variable.
  
  Returns 1 if string data could not be converted to %d.
  */
  long conversion_var = 0;
  int status;
  
  // Parse into %d
  // Returns number of arguments successfully parsed
  status = sscanf(string_data, "%ld", &conversion_var);
    
  //~ Serial.print("DBG SIC ");
  //~ Serial.print(string_data);
  //~ Serial.print("-");
  //~ Serial.print(conversion_var);
  //~ Serial.print("-");
  //~ Serial.print(status);
  //~ Serial.println(".");
  
  if (status == 1) {
    // Good, we converted one variable
    variable = conversion_var;
    return 0;
  }
  else {
    // Something went wrong, probably no variables converted
    Serial.print("ERR SIC cannot parse -");
    Serial.print(string_data);
    Serial.println("-");
    return 1;
  }
}








/* Header file for declaring protocol-specific states.
This implements a passive detection task.

Defines the following
* tpidx_ macros ... these allow you to index into trial_params
* tridx_ macros ... same, but for trial results
* the STATE_TYPE enum, which defines all possible states
* declarations for state functions and state objects, especially those derived
  from TimedState.

To define a new state, you should declare it here and put its implementation
into States.cpp.
*/


#ifndef __STATES_H_INCLUDED__
#define __STATES_H_INCLUDED__

#include "TimedState.h"

//// Global trial parameters structure. This holds the current value of
// all parameters. Should probably also make a copy to hold the latched
// values on each trial.
// Characteristics of each trial. These can all be modified by the user.
// However, there is no guarantee that the newest value will be used until
// the current trial is released.
// Various types:
// * Should be latched, must be set at beginning ("RD_L")
// * Should be latched, can use default here ("SRVFAR")
// * Need to be set on every trial, else error ("STPPOS")
// * Some, like STPSPD, are not being updated
//
// * Init-only: those, like STPSPD, that are only used at the very beginning
// * Init-usually: those, like SRV_FAR, that could be varied later, but
//   the use case is infrequent (or never) and possibly untested.
// * Trial-required: those, like rewside, that must be specified on each trial 
//   or error.
// * Latched: those, like TO, that will often vary within a session
//
// Reported on each trial: trial-required, maybe latched
// Reported initially only: init-only, probably init-usually
// Reported on change only: latched, maybe init-usually
//
// Decision 1: Report latched on each trial or only on change?
// Decision 2: Should init-usually be treated more like latched (see above),
//             or more like init-only?
//
// The main things to add to this code are:
// * Report TRLP only those that are marked "report-on-each-trial"
// * Do not release trial until all "required-on-each-trial" are set
// And we can argue about how these two categories map onto the categories above.
//
// Attempt to have 0 be the "error value" since it cannot intentially be set to 0.
#define N_TRIAL_PARAMS 13
#define tpidx_NSTPS 0 // reqd
#define tpidx_MRT 1 // latch
#define tpidx_ITI 2 // init-usually
#define tpidx_2PSTP 3 // init-only
#define tpidx_RESP_WIN_DUR 4 // init-usually
#define tpidx_INTER_REWARD_INTERVAL 5 // init-usually
#define tpidx_REWARD_DUR_L 6 // init-usually
#define tpidx_REWARD_DUR_R 7 // init-usually
#define tpidx_STEP_SPEED 8 // init-only
#define tpidx_TOU_THRESH 9 // init-only
#define tpidx_REL_THRESH 10 // init-only
#define tpidx_STPT 11 // init-usually
#define tpidx_ISGO 12 // reqd

//// Global trial results structure. Can be set by user-defined states. 
// Will be reported during mandatory INTER_TRIAL_INTERVAL state.
#define N_TRIAL_RESULTS 2
#define tridx_RESPONSE 0
#define tridx_OUTCOME 1



//// Defines for commonly used things
// Move this to TrialSpeak, and rename CHOICE_LEFT etc
#define LEFT 1
#define RIGHT 2
#define NOGO 3

#define OUTCOME_HIT 1
#define OUTCOME_ERROR 2
#define OUTCOME_SPOIL 3

//// States
// Defines the finite state machine for this protocol
enum STATE_TYPE
{
  WAIT_TO_START_TRIAL,
  TRIAL_START,
  MOVE_STEPPER1,
  RESPONSE_WINDOW,
  REWARD_L,
  POST_REWARD_PAUSE,
  INTER_TRIAL_INTERVAL
};

// Declare utility functions
int rotate(long n_steps);

// Declare non-class states
int state_move_stepper1(STATE_TYPE& next_state);
int state_reward_l(STATE_TYPE& next_state);
  

//// Declare states that are objects
// Presently these all derive from TimedState
// Ensure that they have a public constructor, and optionally, a public
// "update" function that allows resetting of their parameters.
//
// Under protected, declare their protected variables, and declare any of
// s_setup, loop(), and s_finish() that you are going to define.
class StateResponseWindow : public TimedState {
  protected:
    uint16_t my_touched = 0;
    unsigned int my_rewards_this_trial = 0;
    void loop();
    void s_finish();
    virtual void set_licking_variables(bool &, bool &);
  
  public:
    void update(uint16_t touched);
    StateResponseWindow(unsigned long d) : TimedState(d) { };
};

class StateInterTrialInterval : public TimedState {
  protected:
    void s_setup();
    void s_finish();
  
  public:
    StateInterTrialInterval(unsigned long d) : TimedState(d) { };
};

class StatePostRewardPause : public TimedState {
  protected:
    void s_finish();
  
  public:
    StatePostRewardPause(unsigned long d) : TimedState(d) { };
};

#endif
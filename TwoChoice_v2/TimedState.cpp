#include "TimedState.h"

void TimedState::run(unsigned long time)
{
  // always store time of last call
  time_of_last_call = time;    
    
  // boiler plate timer code
  if (timer == 0)
  {
    s_setup();
    flag_stop = 0;
    timer = time + duration;
  }
  
  if (flag_stop || (time >= timer))
  {
    s_finish();
    timer = 0;      
  }
  else
  {
    loop();
  }
};


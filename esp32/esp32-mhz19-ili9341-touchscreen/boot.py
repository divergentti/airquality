from machine import reset_cause
#  0 = power on, 6 = hard reset, 1 = WDT reset, 5 = DEEP_SLEEP reset, 4 soft reset
print("Previous boot reason %s" % reset_cause())
print("Continuing to main.py, wait ...")

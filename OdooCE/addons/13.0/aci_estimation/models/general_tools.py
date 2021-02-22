# -*- coding: utf-8 -*-

def get_float_from_time(time):
    minute_arr = str(float(time.minute) / 60).split('.')
    return float('{0}.{1}'.format(time.hour, minute_arr[1]))

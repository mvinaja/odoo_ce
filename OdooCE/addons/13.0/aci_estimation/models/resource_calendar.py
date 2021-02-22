# -*- coding: utf-8 -*-

from datetime import datetime, timedelta
import pytz
from dateutil import rrule

from odoo import models, fields, api
from odoo.tools import DEFAULT_SERVER_DATE_FORMAT, DEFAULT_SERVER_DATETIME_FORMAT


class ResourceCalendar(models.Model):
    _inherit = 'resource.calendar'

    schedule_leave_ids = fields.One2many('schedule.leave',
                                         'calendar_id', string='Schedule Leaves')

    attendance_ids = fields.One2many('resource.calendar.attendance',
                                     'calendar_id', 'Working Time', copy=True)

    # DATE TOOLS

    @api.model
    def get_object_date(self, str_date):
        # return datetime.strptime(str_date, DEFAULT_SERVER_DATE_FORMAT)
        return str_date

    @api.model
    def get_string_date(self, obj_date):
        return obj_date.strftime(DEFAULT_SERVER_DATE_FORMAT)

    @api.model
    def get_string_datetime_with_tz(self, str_datetime):
        return self.get_object_datetime(str_datetime).strftime(DEFAULT_SERVER_DATETIME_FORMAT)

    @api.model
    def get_object_datetime(self, str_datetime):
        return self.get_datetime_with_tz(str_datetime)

    @api.model
    def get_datetime_with_tz(self, obj_datetime):
        tz = fields.Datetime.context_timestamp(self, timestamp=datetime.now()).tzinfo
        return pytz.UTC.localize(obj_datetime).astimezone(tz)

    @api.model
    def get_datetime_utc(self, date):
        return date.astimezone(pytz.UTC)

    @api.model
    def get_datetime_string(self, date):
        return self.get_datetime_utc(date).strftime(DEFAULT_SERVER_DATETIME_FORMAT)

    # TOOLS TO ATTENDANCE

    def get_ranges_of_working_time(self, date_start, date_end, emp_attendance, tolerance=0):
        self.ensure_one()
        # TODO: Attendance para horarios con dias de la semana diferentes
        #       por ejemplo: un horario de 22 hrs - 4 hrs (horario continuo de 2 dias diferentes)
        tolerance /= 60

        start_dt, start_day, end_dt, current_hour, end_hour = self._get_init_values(date_start, date_end)
        ranges = {'incidences': [], 'working': []}
        # Attendance del horario (rangos validos de trabajo). No attendance del empleado
        attendance_ids = self.attendance_ids.filtered(lambda r: int(r.dayofweek) == int(start_day))
        # Control para modificar attendance original que lanzó el proceso
        origin_modified = False
        count = 1
        for attendance in attendance_ids.sorted(key=lambda r: r.hour_from):
            hour_from = attendance.hour_from
            hour_to = attendance.hour_to
            aux_incidence = []
            aux_working = []

            if current_hour > hour_to and count < len(attendance_ids):
                continue

            # Evaluate "employee attendance block (check_in - check_out)"
            # vs hour_from of "schedule attendance"
            origin_modified, current_hour, flag_break = self._evaluate_hour_from(attendance_ids,
                                                                                 hour_from, hour_to, current_hour,
                                                                                 end_hour, tolerance, start_dt, end_dt,
                                                                                 ranges,
                                                                                 aux_incidence, aux_working,
                                                                                 origin_modified, emp_attendance)
            if flag_break:
                break

            # Evaluate "employee attendance block (check_in - check_out)"
            # vs hour_to of "schedule attendance"
            origin_modified, current_hour, flag_break = self._evaluate_hour_to(attendance_ids,
                                                                               hour_from, hour_to, current_hour,
                                                                               end_hour, tolerance, start_dt, end_dt,
                                                                               ranges,
                                                                               aux_incidence, aux_working,
                                                                               origin_modified, emp_attendance, count)
            if flag_break:
                break

            ranges['incidences'] += aux_incidence
            ranges['working'] += aux_working
            count += 1
        return ranges

    def _evaluate_hour_from(self, attendance_ids, hour_from, hour_to, current_hour,
                            end_hour, tolerance, start_dt, end_dt, ranges, aux_incidence, aux_working,
                            origin_modified, emp_attendance):
        self.ensure_one()
        flag_break = False
        blocks_working_before = len(attendance_ids.filtered(lambda r: r.hour_to < hour_from)) > 0
        if blocks_working_before and current_hour < hour_from:
            check_in = self.get_date_with_repl_hour(start_dt, current_hour)
            incidence_name = 'Check on meal schedule'
            aux_incidence.append((0, False, {'check_in': check_in,
                                             'name': incidence_name, 'is_computed': True}))
        elif not blocks_working_before and current_hour < hour_from - tolerance:
            check_in = self.get_date_with_repl_hour(start_dt, current_hour, 'self')
            incidence_name = 'Check before schedule'
            aux_incidence.append((0, False, {'check_in': check_in,
                                             'name': incidence_name, 'is_computed': True}))
            # check_in = self.get_date_with_repl_hour(start_dt, current_hour)
            # incidence_name = Incidence.get_incidence_name(attendance_ids, 'before_start_schedule', hour_from)

        if end_hour <= hour_from:
            if not origin_modified:
                check_in = self.get_date_with_repl_hour(start_dt, current_hour)
                aux_working.append((1, emp_attendance.id, {'check_in': check_in, 'check_out': check_in}))
                origin_modified = True

            check_out = self.get_date_with_repl_hour(end_dt, end_hour, 'self')
            if end_hour - current_hour > tolerance:
                aux_incidence[-1][2]['check_out'] = check_out
            else:
                if aux_incidence and len(aux_incidence) > 0:
                    del (aux_incidence[-1])
                # aux_working[-1][2]['check_out'] = check_out
                if len(aux_working) > 0:
                    aux_working[-1][2]['check_out'] = check_out
                elif len(ranges['working']) > 0:
                    ranges['working'][-1][2]['check_out'] = check_out
            ranges['incidences'] += aux_incidence
            ranges['working'] += aux_working
            flag_break = True
        elif aux_incidence:
            if blocks_working_before:
                check_out = self.get_date_with_repl_hour(start_dt, hour_from)

                if not origin_modified:
                    aux_working.append((1, emp_attendance.id, {'check_in': check_out}))
                    origin_modified = True

                if hour_from - current_hour > tolerance:
                    aux_incidence[-1][2]['check_out'] = check_out
                else:
                    del (aux_incidence[-1])
                    if len(ranges['working']) > 0:
                        ranges['working'][-1][2]['check_out'] = check_out
                current_hour = hour_from
            elif current_hour < hour_from - tolerance:
                check_out = self.get_date_with_repl_hour(start_dt, hour_from - tolerance)

                if not origin_modified:
                    aux_working.append((1, emp_attendance.id, {'check_in': check_out}))
                    origin_modified = True

                aux_incidence[-1][2]['check_out'] = check_out
                current_hour = hour_from - tolerance

        return origin_modified, current_hour, flag_break

    def _evaluate_hour_to(self, attendance_ids, hour_from, hour_to, current_hour,
                          end_hour, tolerance, start_dt, end_dt, ranges, aux_incidence, aux_working,
                          origin_modified, emp_attendance, count):
        self.ensure_one()
        Incidence = self.env['attendance.incidence']
        flag_break = False
        blocks_working_after = len(attendance_ids.filtered(lambda r: r.hour_from > hour_to)) > 0
        if blocks_working_after and end_hour <= float(hour_to):
            check_in = self.get_date_with_repl_hour(start_dt, current_hour)
            check_out = self.get_date_with_repl_hour(end_dt, end_hour, 'self')
            if not origin_modified:
                aux_working.append((1, emp_attendance.id, {'check_out': check_out}))
            elif aux_working and aux_working[-1][0] == 1:
                aux_working[-1][2]['check_out'] = check_out
            else:
                aux_working.append((0, False, {'check_in': check_in, 'check_out': check_out}))

            ranges['working'] += aux_working
            ranges['incidences'] += aux_incidence
            flag_break = True
        elif not blocks_working_after and end_hour <= float(hour_to) + tolerance:
            check_in = self.get_date_with_repl_hour(start_dt, current_hour)
            check_out = self.get_date_with_repl_hour(end_dt, end_hour, 'self')
            if not origin_modified:
                aux_working.append((1, emp_attendance.id, {'check_out': check_out}))
            elif aux_working and aux_working[-1][0] == 1:
                aux_working[-1][2]['check_out'] = check_out
            else:
                aux_working.append((0, False, {'check_in': check_in, 'check_out': check_out}))

            ranges['working'] += aux_working
            ranges['incidences'] += aux_incidence
            flag_break = True
        elif blocks_working_after and current_hour < float(hour_to):
            check_in = self.get_date_with_repl_hour(start_dt, current_hour)
            check_out = self.get_date_with_repl_hour(end_dt, float(hour_to))
            if not origin_modified:
                aux_working.append((1, emp_attendance.id, {'check_out': check_out}))
                origin_modified = True
            elif aux_working and aux_working[-1][0] == 1:
                aux_working[-1][2]['check_out'] = check_out
            else:
                aux_working.append((0, False, {'check_in': check_in, 'check_out': check_out}))
            current_hour = hour_to
        elif not blocks_working_after and current_hour < float(hour_to) + tolerance:
            check_in = self.get_date_with_repl_hour(start_dt, current_hour)
            check_out = self.get_date_with_repl_hour(end_dt, float(hour_to) + tolerance)
            if not origin_modified:
                aux_working.append((1, emp_attendance.id, {'check_out': check_out}))
                origin_modified = True
            elif aux_working and aux_working[-1][0] == 1:
                aux_working[-1][2]['check_out'] = check_out
            else:
                aux_working.append((0, False, {'check_in': check_in, 'check_out': check_out}))
            current_hour = hour_to + tolerance

        # if it's last attendance
        if count == len(attendance_ids) and end_hour > float(hour_to) + tolerance:
            check_in = self.get_date_with_repl_hour(start_dt, current_hour)
            check_out = self.get_date_with_repl_hour(end_dt, end_hour)
            if not origin_modified:
                aux_working.append((1, emp_attendance.id, {'check_in': check_in, 'check_out': check_in}))

            incidence_name = Incidence.get_incidence_name(attendance_ids, 'after_end_schedule', hour_to)
            aux_incidence.append((0, False, {'check_in': check_in,
                                             'check_out': check_out, 'name': incidence_name, 'is_computed': True}))

        return origin_modified, current_hour, flag_break

    # OTHER TOOLS

    def _get_tz_datetime(self, datetime, user_id):
        user_id = user_id if user_id else self.env.user
        tz_datetime = datetime.astimezone(pytz.timezone(str(user_id.tz)))
        return tz_datetime

    def get_check_in_incidences(self, check_in, tolerance):
        self.ensure_one()
        checkIn_utc = datetime.strptime(check_in, DEFAULT_SERVER_DATETIME_FORMAT)
        check_in_dt = self._get_tz_datetime(checkIn_utc, self.env.user)
        weekday = check_in_dt.weekday()
        check_in_hour = self._get_float_hour(check_in_dt)

        attendance_ids = self.attendance_ids \
            .filtered(lambda r: int(r.dayofweek) == int(weekday) and r.hour_to > check_in_hour)
        if attendance_ids:
            attendance_id = attendance_ids[0]
            if check_in_hour > attendance_id.hour_from + (tolerance / 60):
                return True

        return False

    # def get_date_with_repl_hour(self, date, final_hour):
    def get_date_with_repl_hour(self, date, final_hour=0.0, second='0'):
        self.ensure_one()
        hour_arr = str(final_hour).split('.')
        hour = int(hour_arr[0])
        minute = int(round(60 * float('.' + hour_arr[1])))
        if second == 'self':
            second = date.second
        return (date.replace(hour=hour, minute=minute, second=int(second)).astimezone(pytz.UTC)).strftime(
            DEFAULT_SERVER_DATETIME_FORMAT)

    @api.model
    def _get_date_object(self, str_date):
        return self._get_date_tz(datetime.strptime(str_date, DEFAULT_SERVER_DATETIME_FORMAT))

    @api.model
    def _get_date_tz(self, date):
        timezone = fields.Datetime.context_timestamp(self, timestamp=datetime.now()).tzinfo
        return pytz.UTC.localize(date).astimezone(timezone)

    @api.model
    def _get_float_hour(self, date):
        minute_arr = str(float(date.minute) / 60).split('.')
        return float('{0}.{1}'.format(date.hour, minute_arr[1]))

    @api.model
    def _get_init_values(self, date_start, date_end):
        date_start_utc = datetime.strptime(date_start, DEFAULT_SERVER_DATETIME_FORMAT)
        date_end_utc = datetime.strptime(date_end, DEFAULT_SERVER_DATETIME_FORMAT)
        start_dt = self._get_tz_datetime(date_start_utc, self.env.user)
        start_day = start_dt.weekday()
        end_dt = self._get_tz_datetime(date_end_utc, self.env.user)
        # end_day = end_dt.weekday()
        current_hour = self._get_float_hour(start_dt)
        end_hour = self._get_float_hour(end_dt)
        return start_dt, start_day, end_dt, current_hour, end_hour

    def get_limit_hrs(self, date_from, date_to, employee_atts, holidays=False):
        self.ensure_one()
        intervals = self.get_interval_working_dates(date_from, date_to)
        intervals = self.get_interval_dates_without_leaves(intervals, employee_atts, holidays=holidays)
        # working_hrs = self.get_working_hours(date_from, date_to)
        return self.get_limit_hours(intervals)

    def get_interval_period_dates(self, date_from, date_to):

        if not self:
            return self.get_all_interval_period_dates(date_from, date_to)

        interval = self.get_interval_working_dates(date_from, date_to)
        if len(interval):
            return interval.keys()
        return []

    def _get_weekdays(self):
        """ Return the list of weekdays that contain at least one working
        interval. """
        self.ensure_one()
        return list({int(d) for d in self.attendance_ids.mapped('dayofweek')})

    def get_interval_working_dates(self, date_from, date_to):
        self.ensure_one()
        tz = fields.Datetime.context_timestamp(self, timestamp=datetime.now()).tzinfo
        dates = []
        for day in rrule.rrule(rrule.DAILY, dtstart=date_from,
                               # until=(date_to + timedelta(days=1)).replace(hour=0, minute=0, second=0),
                               until=datetime.combine(date_to, datetime.min.time()).replace(hour=23, minute=59,
                                                                                            second=59),
                               byweekday=self._get_weekdays()):
            day_start_dt = day.replace(hour=0, minute=0, second=0, tzinfo=tz).astimezone(pytz.UTC)
            day_end_dt = day.replace(hour=23, minute=59, second=59, tzinfo=tz).astimezone(pytz.UTC)
            hours = self.get_work_hours_count(day_start_dt, day_end_dt, False)
            dates.append((day.date(), hours))
        return dict(dates)

    def get_all_interval_period_dates(self, date_from, date_to):
        weedays = [(date_from + timedelta(days=offset)).weekday() for offset in range((date_to - date_from).days + 1)]
        dates = []
        for day in rrule.rrule(rrule.DAILY, dtstart=date_from,
                               # until=(date_to + timedelta(days=1)).replace(hour=0, minute=0, second=0),
                               until=datetime.combine(date_to, datetime.min.time()).replace(hour=23, minute=59,
                                                                                            second=59),
                               byweekday=weedays):
            # day_start_dt = day.replace(hour=0, minute=0, second=0)
            # day_end_dt = day.replace(hour=23, minute=59, second=59)
            dates.append(day.date())
        return dates

    @api.model
    def get_interval_dates_without_leaves(self, working_dates, employee_atts, holidays=False):
        dates = [] if not holidays else map(lambda k: k.date(), holidays.keys())
        # return dict(filter(lambda d, dat: d in employee_atts\
        #     and d not in dates, working_dates.items()))
        return dict([(d, dat) for d, dat in working_dates.items() if d in employee_atts and d not in dates])

    @api.model
    def get_limit_hours(self, working_dates):
        return sum(map(lambda v: v, working_dates.values()))

    def working_hours_on_day(self, date):
        tz = fields.Datetime.context_timestamp(self, timestamp=datetime.now()).tzinfo
        from_date = date.replace(hour=0, minute=0, second=0, tzinfo=tz).astimezone(pytz.UTC)
        to_date = date.replace(hour=23, minute=59, second=59, tzinfo=tz).astimezone(pytz.UTC)
        hours = self.get_work_hours_count(from_date, to_date, False)
        return hours

    def get_extremes_by_day(self):
        self.ensure_one()
        attendance = dict(self.attendance_ids.mapped(lambda r: \
                                                         ((r.id, int(r.dayofweek)), [r.hour_from, r.hour_to])))
        response = {}
        for k, h in attendance.items():
            response.setdefault(k[1], [])
            h_f = len(response[k[1]]) > 0 and min([response[k[1]][0], h[0]]) or h[0]
            h_t = len(response[k[1]]) > 1 and max([response[k[1]][1], h[1]]) or h[1]
            response[k[1]] = [h_f, h_t]
        return response

    def get_schedule_distribution(self):
        self.ensure_one()
        return {
            'schedule_working': self._get_working_schedule_map(),
            'schedule_leave': self._get_schedule_leave_map()
        }

    def _get_working_schedule_map(self):
        self.ensure_one()
        attendance = dict(self.attendance_ids.mapped(lambda r: \
                                                         ((r.id, int(r.dayofweek)), [r.hour_from, r.hour_to])))
        response = {}
        for k, h in attendance.items():
            response.setdefault(k[1], []).append(h)
        return response

    def _get_schedule_leave_map(self):
        self.ensure_one()
        leaves = dict(self.schedule_leave_ids.mapped(lambda r: \
                                                         ((r.id, int(r.dayofweek)), [r.hour_from, r.hour_to])))
        response = {}
        for k, h in leaves.items():
            response.setdefault(k[1], []).append(h)
        return response

    def get_work_hours_count(self, start_dt, end_dt, resource_id, compute_leaves=True):
        straight_time = super(ResourceCalendar, self).get_work_hours_count(start_dt, end_dt, resource_id,
                                                                           compute_leaves)
        leave_hrs = self.schedule_leave_ids \
            .filtered(lambda r: int(r.dayofweek) == start_dt.weekday()).mapped('hours')
        return straight_time - sum(leave_hrs)

    def validate_check_in(self, check_in, tolerance):
            self.ensure_one()
            checkIn_utc = datetime.strptime(check_in, DEFAULT_SERVER_DATETIME_FORMAT)
            check_in_dt = self._get_tz_datetime(checkIn_utc, self.env.user)
            weekday = check_in_dt.weekday()
            check_in_hour = self._get_float_hour(check_in_dt)
            attendance_ids = self.attendance_ids \
                .filtered(lambda r: int(r.dayofweek) == int(weekday) and r.hour_to > check_in_hour)
            if attendance_ids:
                attendance_id = attendance_ids[0]
                if check_in_hour < attendance_id.hour_from + (tolerance / 60):
                    return True
            return False

    def validate_tolerance_sign_out(self, check_in, tolerance):
        self.ensure_one()
        checkIn_utc = datetime.strptime(check_in, DEFAULT_SERVER_DATETIME_FORMAT)
        check_in_dt = self._get_tz_datetime(checkIn_utc, self.env.user)
        weekday = check_in_dt.weekday()
        check_in_hour = self._get_float_hour(check_in_dt)
        attendance_ids = self.attendance_ids \
            .filtered(lambda r: int(r.dayofweek) == int(weekday) and r.hour_from <= check_in_hour and r.hour_to + (tolerance / 60) >= check_in_hour)
        if attendance_ids:
            return True
        return


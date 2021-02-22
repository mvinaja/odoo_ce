# -*- coding: utf-8 -*-

from datetime import datetime, date, timedelta
from calendar import monthrange
import pytz

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from odoo.tools import DEFAULT_SERVER_DATE_FORMAT


class PaymentPeriodGroup(models.Model):
    _name = 'payment.period.group'
    _description = 'payment.period.group'

    def _get_years(self):
        return [(str(i), i) for i in range(fields.Date.today().year - 1, 2050, 1)]

    name = fields.Char(required=True)
    initial_year = fields.Selection(selection='_get_years', required=True)
    plan_year = fields.Selection(selection='_get_years')
    nomenclature = fields.Char(default='{count}_{year}_', required=True)
    type_condition = fields.Selection([('day', 'Day of the Week'),
                                       ('number', 'Number of the day')], default='day', required=True)
    day_condition_ids = fields.One2many('payment.period.day.condition', 'group_id')
    number_condition_ids = fields.One2many('payment.period.number.condition', 'group_id')
    period_ids = fields.One2many('payment.period', 'group_id')
    has_periods = fields.Boolean(compute="_compute_period")
    tracking_window = fields.Integer('Tracking window', default=1)
    calendar_week = fields.Boolean(default=False)
    format_language = fields.Many2one('res.lang')
    week_start = fields.Selection([
        ('0', 'Monday'),
        ('1', 'Tuesday'),
        ('2', 'Wednesday'),
        ('3', 'Thursday'),
        ('4', 'Friday'),
        ('5', 'Saturday'),
        ('6', 'Sunday'),
    ], compute='_compute_week_start', store=True, readonly=False)

    def write(self, values):
        res = super(PaymentPeriodGroup, self).write(values)
        if self.period_ids and ('type_condition' in values.keys() or 'day_condition_ids' in values.keys() or 'number_condition_ids' in values.keys()):
            raise ValidationError('Delete period_ids to change this configuration')
        return res

    @api.model
    def create(self, values):
        # Calendar Week
        if values.get('calendar_week'):
            values['type_condition'] = 'day'
            week_start = values.get('week_start')
            week_end = str(int(week_start) - 1) if week_start != '0' else '6'
            values['day_condition_ids'] = [(0, False, {'display_type': False,
                                                       'day': week_start,
                                                       'sequence': 0}),
                                           (0, False, {'display_type': False,
                                                       'day': week_end,
                                                       'sequence': 0})]
            # Calculate first week
            initial_year = int(values.get('initial_year'))
            day_1 = date(initial_year, 1, 1)
            day = day_1
            while day.isoweekday() - 1 != int(week_start):
                day = day - timedelta(days=1)
            first_week_start = day
            day = day_1
            while day.isoweekday() - 1 != int(week_end):
                day = day + timedelta(days=1)
            first_week_end = day

            # Build Record data
            Period = self.env['payment.period']
            start = datetime.combine(first_week_start, datetime.min.time()).replace(hour=0, minute=0, second=0, microsecond=0)
            end = datetime.combine(first_week_end, datetime.min.time()).replace(hour=23, minute=59, second=59, microsecond=0)
            # Create Periods
            cmds = []
            from_date = self.env['time.tracking.actions'].remove_tz_datetime(start, self.env.user)
            to_date = self.env['time.tracking.actions'].remove_tz_datetime(end, self.env.user)
            sequence = 1
            global_sequence = 1
            year = str(initial_year)
            while to_date.year <= initial_year:
                str_sequence = '{}' if sequence > 9 else '0{}'
                name = values.get('nomenclature').replace('{count}', str_sequence.format(sequence)).replace(
                    '{year}', year[2:])
                period = Period.create({'name': name,
                                        'global_sequence': global_sequence,
                                        'sequence': sequence,
                                        'from_date': from_date,
                                        'to_date': to_date,
                                        'year': year})
                cmds.append((4, period.id))
                from_date = from_date + timedelta(days=7)
                to_date = to_date + timedelta(days=7)
                sequence += 1
                global_sequence += 1
            values['period_ids'] = cmds

        if values.get('type_condition') == 'day':
            day_condition_ids = values.get('day_condition_ids')
            if not day_condition_ids or len(day_condition_ids) <= 1:
                raise ValidationError('You need at least 2 conditions.')
            element = 1
            days = 0
            for condition in day_condition_ids:
                if element == 1 and condition[2]['display_type']:
                    raise ValidationError('You can not have a WEEK as a first condition.')
                elif element == len(day_condition_ids) and condition[2]['display_type']:
                    raise ValidationError('You can not end the conditions with a WEEK.')
                elif not condition[2]['display_type']:
                    days += 1
                element += 1
            if days != 2:
                raise ValidationError('If you want to use the day of the week on the conditions '
                                      'you only have to select 2 days')
        else:
            number_condition_ids = values.get('number_condition_ids')
            if not number_condition_ids or len(number_condition_ids) <= 1:
                raise ValidationError('You need at least 2 conditions.')
            numbers = []
            has_fd = False
            has_ld = False
            element = 1
            for condition in number_condition_ids:
                if element == 1 and condition[2]['number'] != 'fd':
                    raise ValidationError('You need to start the month with the FIRST DAY')
                elif element == len(number_condition_ids) and condition[2]['number'] != 'ld':
                    raise ValidationError('You need to end the month with the LAST DAY')

                if condition[2]['number'] == 'fd':
                    has_fd = True
                elif condition[2]['number'] == 'ld':
                    has_ld = True
                if has_ld and not has_fd:
                    raise ValidationError('First Day is always before Last Day')
                if numbers:
                    numbers.sort()
                    if condition[2]['number'] not in ['fd', 'ld'] and numbers[-1] >= condition[2]['number']:
                        raise ValidationError('You numbers day needs to be in order')
                if condition[2]['number'] not in ['fd', 'ld']:
                    numbers.append(int(condition[2]['number']))
                element += 1
            if not has_ld or not has_fd:
                raise ValidationError('You need to add first and day last as a condition to close the Month')
        return super(PaymentPeriodGroup, self).create(values)

    @api.depends('period_ids')
    def _compute_period(self):
        for r in self:
            r.has_periods = True if r.period_ids else False

    @api.depends('format_language')
    def _compute_week_start(self):
        for r in self:
            r.week_start = str(int(r.format_language.week_start) - 1) if r.format_language.week_start else '0'

    def delete_periods_button(self):
        self.period_ids.unlink()

    def update_nomenclature_button(self):
        for period_id in self.period_ids:
            str_sequence = '{}' if period_id.sequence > 9 else '0{}'
            period_id.name = self.nomenclature.replace('{count}', str_sequence.format(period_id.sequence)).replace(
                '{year}', period_id.year[2:])

    def open_plan_year(self):
        return {
            'name': 'Select a year to generate periods',
            'view_mode': 'form',
            'res_model': 'payment.period.group',
            'view_id': self.env.ref('aci_estimation.payment_group_plan_year_form_view').id,
            'type': 'ir.actions.act_window',
            'target': 'new',
            'res_id': self.id
        }

    def compute_periods_button(self):
        if self.plan_year and self.plan_year < self.initial_year:
            raise ValidationError('The selected year must be bigger than the initial year.')
        year = int(self.initial_year)
        while year <= int(self.plan_year):
            if str(year) not in self.env['payment.period'].search([('group_id', '=', self.id)]).mapped('year'):
                day = datetime.strptime('{}-01-01'.format(year), DEFAULT_SERVER_DATE_FORMAT)
                sequence = 1
                global_sequence = 1
                for period_id in self.period_ids:
                    global_sequence = period_id.global_sequence if period_id.global_sequence > global_sequence else global_sequence
                if self.type_condition == 'day':
                    first_period = True
                    if global_sequence > 1:
                        day = self.env['payment.period'].search([('global_sequence', '=', global_sequence),
                                                                 ('group_id', '=', self.id)]).to_date
                        first_period = False
                        global_sequence += 1
                    period_start, period_end = self.periods_by_day(day, first_period)
                    self.create_period(global_sequence, sequence, period_start, period_end)
                    valid_period = True
                    while valid_period:
                        sequence += 1
                        global_sequence += 1
                        period_start, period_end = self.periods_by_day(period_end + timedelta(days=1))
                        if period_end.year <= int(year):
                            valid_period = True
                            self.create_period(global_sequence, sequence, period_start, period_end)
                        else:
                            valid_period = False
                else:
                    global_sequence += 1
                    month_periods = self.periods_by_number(day)
                    for period in month_periods:
                        self.create_period(global_sequence, sequence, period[0], period[1])
                        global_sequence += 1
                        sequence += 1
                    while (month_periods[len(month_periods) - 1][1] + timedelta(days=1)).year <= int(year):
                        month_periods = self.periods_by_number(month_periods[len(month_periods) - 1][1] + timedelta(days=1))
                        for period in month_periods:
                            self.create_period(global_sequence, sequence, period[0], period[1])
                            sequence += 1
                            global_sequence += 1
            year += 1
        self.plan_year = None

    def periods_by_day(self, day, first_period=False):
        period_start = None
        period_end = None
        for condition in self.day_condition_ids:
            if not condition.display_type:
                found_day = False
                while not found_day:
                    found_day = True if day.weekday() == int(condition.day) else False
                    if first_period:
                        day = day - timedelta(days=1)
                        first_period = False if day.weekday() == int(condition.day) else True
                    else:
                        day = day + timedelta(days=1)
                period_end = day - timedelta(days=1) if period_start else period_end
                period_start = day - timedelta(days=1) if not period_start else period_start
            else:
                day = day + timedelta(days=7)
        return period_start.replace(hour=0, minute=0, second=0), period_end.replace(hour=23, minute=59, second=59)

    def periods_by_number(self, day):
        period_start = None
        period_end = None
        month_periods = []
        for condition in self.number_condition_ids:
                found_day = False
                while not found_day:
                    if condition.number == 'fd':
                        day_number = 1
                    elif condition.number == 'ld':
                        day_number = monthrange(day.year, day.month)[1]
                    else:
                        day_number = int(condition.number)
                    found_day = True if day.day == day_number else False
                    day = day + timedelta(days=1)
                period_end = day - timedelta(days=1) if period_start else period_end
                period_start = day - timedelta(days=1) if not period_start else period_start
                if period_start and period_end:
                    month_periods.append((period_start.replace(hour=0, minute=0, second=0),
                                          period_end.replace(hour=23, minute=59, second=59)))
                    period_start = period_end.replace(hour=0, minute=0, second=0) + timedelta(days=1)
                    period_end = None
        return month_periods

    def _get_tz_datetime(self, wanted_datetime, user_id=None):
        user_id = user_id if user_id else self.env.user
        tz = str(user_id.tz) if user_id.tz else 'Mexico/General'
        return pytz.timezone(tz).localize(wanted_datetime.replace(tzinfo=None), is_dst=False).astimezone(
            pytz.UTC).replace(tzinfo=None)

    def create_period(self, global_sequence, sequence, start, end):
        str_sequence = '{}' if sequence > 9 else '0{}'
        name = self.nomenclature.replace('{count}', str_sequence.format(sequence)).replace('{year}', str(start.year)[2:])
        Period = self.env['payment.period']
        start = self._get_tz_datetime(start)
        end = self._get_tz_datetime(end)
        record = {'name': name,
                  'global_sequence': global_sequence,
                  'sequence': sequence,
                  'from_date': start,
                  'to_date': end,
                  'year': str(end.year)}
        period_id = Period.search([('from_date', '=', start),
                                   ('to_date', '=', end),
                                   ('group_id', '=', self.id)])
        if not period_id:
            period = self.env['payment.period'].create(record)
            self.period_ids = [(4, period.id)]
        else:
            period_id.name = name
            period_id.write(record)


class PaymentPeriodDayCondition(models.Model):
    _name = 'payment.period.day.condition'
    _description = 'payment.period.day.condition'

    group_id = fields.Many2one('payment.period.group')
    sequence = fields.Integer(required=True)
    display_type = fields.Selection([
        ('line_section', 'Week')
    ], default=False, help="Technical field for UX purpose.")
    week = fields.Char(default='WEEK', string='', readonly=1)
    day = fields.Selection([
        ('0', 'Monday'),
        ('1', 'Tuesday'),
        ('2', 'Wednesday'),
        ('3', 'Thursday'),
        ('4', 'Friday'),
        ('5', 'Saturday'),
        ('6', 'Sunday'),
    ], default='0', required=True)

class PaymentPeriodNumberCondition(models.Model):
    _name = 'payment.period.number.condition'
    _description = 'payment.period.number.condition'

    group_id = fields.Many2one('payment.period.group')
    sequence = fields.Integer(required=True)
    week = fields.Char(default='WEEK', string='', readonly=1)
    number = fields.Selection([
        ('fd', 'Month first day'),
        ('ld', 'Month last day'),
        ('1', '1'),
        ('2', '2'),
        ('3', '3'),
        ('4', '4'),
        ('5', '5'),
        ('6', '6'),
        ('7', '7'),
        ('8', '8'),
        ('9', '9'),
        ('10', '10'),
        ('11', '11'),
        ('12', '12'),
        ('13', '13'),
        ('14', '14'),
        ('15', '15'),
        ('16', '16'),
        ('17', '17'),
        ('18', '18'),
        ('19', '19'),
        ('20', '20'),
        ('21', '21'),
        ('22', '22'),
        ('23', '23'),
        ('24', '24'),
        ('25', '25'),
        ('26', '26'),
        ('27', '27'),
        ('28', '28'),
        ('29', '29'),
        ('30', '30'),
        ('31', '31'),
        ], default='fd', string='Day Number', required=True)

class PaymentPeriod(models.Model):
    _name = 'payment.period'
    _description = 'payment.period'
    _order = 'global_sequence'

    def _get_years(self):
        return [(str(i), i) for i in range(fields.Date.today().year - 5, 2050, 1)]

    group_id = fields.Many2one('payment.period.group', string='Payment Type', ondelete='cascade')
    name = fields.Char('Name')
    global_sequence = fields.Integer('Global Sequence')
    sequence = fields.Integer('Sequence')
    from_date = fields.Datetime('From Date')
    to_date = fields.Datetime('To Date')
    year = fields.Selection(selection='_get_years', store=True, readonly=True)

    def name_get(self):
        res = []
        for _id in self:
            time_position = _id._get_time_position()
            if time_position:
                time_position = ' (' + time_position + ')'
            res.append((_id.id, _id.name + time_position))
        return res

    def _get_time_position(self):
        self.ensure_one()
        now = datetime.now()
        current_period = None
        for period_id in self.group_id.period_ids:
            if period_id.from_date < now <= period_id.to_date:
                current_period = period_id
        previous_period = self.search([('group_id', '=', self.group_id.id),
                                       ('global_sequence', '=', self.global_sequence - 1)])
        next_period = self.search([('group_id', '=', self.group_id.id),
                                   ('global_sequence', '=', self.global_sequence + 1)])
        if previous_period and previous_period.id == self.id:
            return 'Previous Period'
        elif current_period and current_period.id == self.id:
            return 'Current Period'
        elif next_period and next_period.id == self.id:
            return 'Next Period'
        else:
            return ''
# -*- coding: utf-8 -*-

from odoo import models, fields, api
from odoo.tools import DEFAULT_SERVER_DATETIME_FORMAT
from datetime import datetime, timedelta

class HrZkDeviceBlockWizard(models.TransientModel):
    _name = 'hr.zk.device.block.wizard'
    _description = 'hr.zk.device.block.wizard'

    @api.model
    def _get_years_options(self):
        vals = []
        pointer_year = 2017
        while pointer_year < 2050:
            vals.append((str(pointer_year), str(pointer_year)))
            pointer_year += 1
        return vals

    @api.model
    def _get_hour_options(self):
        vals = []
        pointer_hour = 0
        while pointer_hour < 24:
            hour = '%02d' % (pointer_hour)
            vals.append((hour, hour))
            pointer_hour += 1
        return vals

    @api.model
    def _get_minutes_options(self):
        vals = []
        pointer_minutes = 0
        while pointer_minutes < 60:
            minutes = '%02d' % (pointer_minutes)
            vals.append((minutes, minutes))
            pointer_minutes += 1
        return vals

    @api.model
    def _get_default_year(self):
        return str(datetime.now().year)

    year = fields.Selection(
        selection=_get_years_options, default=_get_default_year, index=True)
    payment_period_grp = fields.Many2one('payment.period.group', 'Payment Period Group')
    period_id = fields.Many2one('payment.period', 'Period', ondelete='restrict')
    date_from = fields.Date('Date From', compute='_compute_period_dates')
    date_to = fields.Date('Date To', compute='_compute_period_dates')
    employee_ids = fields.Many2many('hr.employee', string='Employees')

    all_employees = fields.Boolean('All Employees', default=True)

    hour = fields.Selection(selection=_get_hour_options)
    minutes = fields.Selection(selection=_get_minutes_options)
    dayofweek = fields.Selection([
        ('0', 'Monday'),
        ('1', 'Tuesday'),
        ('2', 'Wednesday'),
        ('3', 'Thursday'),
        ('4', 'Friday'),
        ('5', 'Saturday'),
        ('6', 'Sunday')
    ], 'Day of Week')
    date = fields.Date()
    origin = fields.Selection([('block', 'Block'), ('attendance', 'Attendance'), ('log', 'Log')])


    @api.depends('period_id')
    def _compute_period_dates(self):
        for _id in self:
            if _id.period_id:
                _id.date_from = _id.period_id.from_date
                _id.date_to = _id.period_id.to_date

    @api.onchange('year')
    def onchange_year(self):
        self.payment_period_grp = False
        self.period_id = False
        return {'domain': {'payment_period_grp': [('year', '=', self.year)]}}

    @api.onchange('payment_period_grp')
    def onchange_payment_period_grp(self):
        if self.payment_period_grp:
            PeriodGpo = self.env['payment.period.group']
            period_gpo = PeriodGpo.search([('id', '=', self.payment_period_grp.id)])
            prev_period = period_gpo.get_current_period()
            self.period_id = prev_period.id

    def generate_block_button(self):
        utc_date_from = datetime.strptime('{} 12:00:00'.format(self.date_from), DEFAULT_SERVER_DATETIME_FORMAT)
        date_from = self.env['hr.zk.device.log'].get_tz_datetime(utc_date_from, self.env.user)
        today = self.env['hr.zk.device.log'].get_tz_datetime(datetime.now(), self.env.user)
        Log = self.env['hr.zk.device.log']
        while date_from.strftime('%Y-%m-%d') <= self.date_to.strftime('%Y-%m-%d'):
            current_day = True if date_from.strftime('%Y-%m-%d') == today.strftime('%Y-%m-%d') else False

            empl_arg = ('employee_id', 'in', self.employee_ids.ids) if not self.all_employees else ('id', '>', 0)

            day_start = date_from.replace(hour=0, minute=0, second=0, microsecond=1).strftime(
                DEFAULT_SERVER_DATETIME_FORMAT)
            day_end = date_from.replace(hour=23, minute=59, second=59, microsecond=0).strftime(
                DEFAULT_SERVER_DATETIME_FORMAT)

            self.env['hr.zk.device.block'].search([empl_arg, ('date_start', '>=', day_start),
                                                   ('date_start', '<=', day_end),
                                                   ('date_start', '>=', day_start)]).unlink()
            Log.create_block(utc_date_from, current_day=current_day) if self.all_employees\
                else Log.create_block(utc_date_from, [e.id for e in self.employee_ids], current_day)

            date_from = date_from + timedelta(days=1)
            utc_date_from = utc_date_from + timedelta(days=1)

    def generate_attendance_button(self):
        utc_date_from = datetime.strptime('{} 12:00:00'.format(self.date_from), DEFAULT_SERVER_DATETIME_FORMAT)
        date_from = self.env['hr.zk.device.log'].get_tz_datetime(utc_date_from, self.env.user)
        today = self.env['hr.zk.device.log'].get_tz_datetime(datetime.now(), self.env.user)
        Log = self.env['hr.zk.device.log']
        while date_from.strftime('%Y-%m-%d') <= self.date_to.strftime('%Y-%m-%d'):
            current_day = True if date_from.strftime('%Y-%m-%d') == today.strftime('%Y-%m-%d') else False
            Log.create_attendance(utc_date_from, current_day=current_day) if self.all_employees \
                else Log.create_attendance(utc_date_from, [e.id for e in self.employee_ids], current_day)
            date_from = date_from + timedelta(days=1)
            utc_date_from = utc_date_from + timedelta(days=1)

    def generate_missing_log_button(self):
        utc_date_from = datetime.combine(self.date_from, datetime.min.time()).replace(hour=12, minute=0, second=0,
                                                                                      microsecond=0)
        date_from = self.env['hr.zk.device.log'].get_tz_datetime(utc_date_from, self.env.user)
        today = self.env['hr.zk.device.log'].get_tz_datetime(datetime.now(), self.env.user)
        Log = self.env['hr.zk.device.log']
        while date_from.strftime('%Y-%m-%d') <= self.date_to.strftime('%Y-%m-%d'):
            current_day = True if date_from.strftime('%Y-%m-%d') == today.strftime('%Y-%m-%d') else False
            if not current_day:
                Log.create_missing_log(utc_date_from) if self.all_employees \
                    else Log.create_missing_log(utc_date_from, [e.id for e in self.employee_ids])
            date_from = date_from + timedelta(days=1)
            utc_date_from = utc_date_from + timedelta(days=1)


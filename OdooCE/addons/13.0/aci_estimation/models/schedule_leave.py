# -*- coding: utf-8 -*-

from odoo import models, fields, api
from odoo.exceptions import ValidationError


class ScheduleLeave(models.Model):
    _name = 'schedule.leave'
    _description = 'schedule.leave'
    _order = 'dayofweek, hour_from, hour_to'

    name = fields.Char()
    dayofweek = fields.Selection([
        ('0', 'Monday'),
        ('1', 'Tuesday'),
        ('2', 'Wednesday'),
        ('3', 'Thursday'),
        ('4', 'Friday'),
        ('5', 'Saturday'),
        ('6', 'Sunday')
    ], 'Day of Week', required=True, index=True, default='0')
    hour_from = fields.Float('Hour from')
    hour_to = fields.Float('Hour to')
    hours = fields.Float('Hours', compute='_compute_hours', store=True, readonly=True)
    calendar_id = fields.Many2one('resource.calendar', ondelete='cascade')

    @api.constrains('hour_from', 'hour_to')
    def check_dates(self):
        if self.filtered(lambda leave: leave.hour_from >= leave.hour_to):
            raise ValidationError(_('Error! leave start-hour must be lower than leave end-hour.'))

    @api.depends('hour_from', 'hour_to')
    def _compute_hours(self):
        for leave in self:
            if leave.hour_to:
                leave.hours = round(leave.hour_to - leave.hour_from, 2)

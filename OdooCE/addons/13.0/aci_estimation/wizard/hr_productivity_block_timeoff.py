# -*- coding: utf-8 -*-

from odoo import models, fields, api
from odoo.tools import DEFAULT_SERVER_DATETIME_FORMAT
from datetime import datetime, timedelta
from odoo.exceptions import ValidationError

class HrProducitivityBlockTimeoff(models.TransientModel):
    _name = 'hr.productivity.block.timeoff'
    _description = 'hr.productivity.block.timeoff'

    def _get_block_ids(self):
        ctx = self.env.context
        employee_id = ctx.get('default_employee_id')
        date = ctx.get('default_date')
        date = date.split('.')[0]
        date = datetime.strptime(date, DEFAULT_SERVER_DATETIME_FORMAT)
        block_ids = self.env['hr.productivity.block'].search([('employee_id', '=', employee_id),
                                                         ('block_origin', '=', 'timeoff')])
        ids = []
        for _ids in block_ids:
            _date = self.env['time.tracking.actions'].get_tz_datetime(_ids.final_start_date, self.env.user)
            if _date.strftime("%Y-%m-%d") == date.strftime("%Y-%m-%d"):
                ids.append(_ids.id)
        return [('id', 'in', ids)]

    employee_id = fields.Many2one('hr.employee')
    date = fields.Datetime('Day')
    block_id = fields.Many2one('hr.productivity.block', domain=_get_block_ids, required=True, ondelete='restrict')
    start = fields.Datetime(related='block_id.final_start_date')
    end = fields.Datetime(related='block_id.final_end_date')
    time = fields.Float('Time', required=True)

    def button_timeoff(self):
        block_start = self.block_id.final_start_date
        start = block_start.replace(hour=int(self.time), minute=int((self.time - int(self.time))*60),
                                                       second=0)
        utc_start = self.env['time.tracking.actions'].remove_tz_datetime(start, self.env.user)

        incidence_id = self.env['attendance.incidence'].search([('employee_id', '=', self.employee_id.id),
                                                                ('check_in', '<=', utc_start),
                                                                ('check_out', '>=', utc_start),
                                                                ('state', '=', 'approved')])
        if incidence_id:
            raise ValidationError("You cannot take a timeOff inside a Approved incidence")

        utc_end = utc_start + timedelta(minutes=self.block_id.fixed_duration)
        self.block_id.write({'offset_start_date': utc_start,
                             'offset_end_date': utc_end})
        if utc_start < datetime.now():
            self.env['hr.productivity.block'].move_tracking(self.employee_id, utc_start, utc_end)

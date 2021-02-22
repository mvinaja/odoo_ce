# -*- coding: utf-8 -*-

from odoo import models, fields, api
from datetime import datetime
import hashlib


class HrZkDeviceLogWizard(models.TransientModel):
    _name = 'hr.zk.device.log.wizard'
    _description = 'hr.zk.device.log.wizard'

    employee_id = fields.Many2one('hr.employee', string='Employee', ondelete='cascade')
    log_date = fields.Datetime()

    @api.model
    def default_get(self, fields):
        res = super(HrZkDeviceLogWizard, self).default_get(fields)
        res['employee_id'] = self._context.get('employee_id', None)
        return res

    def generate_log_button(self):
        key = hashlib.new('sha1', bytes('{}.{}'.format(datetime.timestamp(self.log_date), self.employee_id.pin).encode())).hexdigest()
        self.env['hr.zk.device.log'].create({'key': key, 'host': None, 'device_user_id': self.employee_id.pin,
                                             'check_date': self.log_date, 'state': 'manual'})
        return {'type': 'ir.actions.client', 'tag': 'reload'}
# -*- coding: utf-8 -*-

from datetime import datetime
from odoo import models, fields, api


class HrProductivityBlockIncidence(models.TransientModel):
    _name = 'hr.productivity.block.incidence'
    _description = 'hr.productivity.block.incidence'

    def _get_incidence(self):
        incidences = [('leave', 'Leave Not Payable'), ('omission', 'Worker Omission')]
        if self.env.user.has_group('aci_estimation.group_estimation_manager'):
            incidences.append(('work_not_payable', 'Work Not Payable'))
            incidences.append(('holiday', 'Holiday Payable by Law'))
            incidences.append(('holiday_company', 'Holiday Payable by Company'))
            incidences.append(('paid_holiday', 'Paid Holiday by Law'))
            incidences.append(('paid_holiday_company', 'Paid Holiday by Company'))
        return incidences

    type_incidence = fields.Selection(_get_incidence, 'Type', required=True, default='leave')
    description = fields.Text(required=True)

    def convert_incidence_btn(self):
        active_ids = self.env.context.get('active_ids', []) or []
        block_ids = self.env['hr.productivity.block'].browse(active_ids)
        employee_ids = block_ids.mapped('employee_id')
        for employee_id in employee_ids:
            employee_block_ids = block_ids.filtered(lambda r: r.employee_id == employee_id)
            end_incidence = None
            start_incidence = None
            for block_id in employee_block_ids.sorted(key=lambda r: r.final_start_date):
                if not end_incidence:
                    end_incidence = block_id.final_end_date
                    start_incidence = block_id.final_start_date
                else:
                    if end_incidence == block_id.final_start_date:
                        end_incidence = block_id.final_end_date
                    else:
                        self.env['attendance.incidence'].create({'check_in': start_incidence,
                                                                 'check_out': end_incidence,
                                                                 'employee_id': employee_id.id,
                                                                 'name': self.description,
                                                                 'productivity_block': True,
                                                                 'approve': False,
                                                                 'type_incidence': self.type_incidence})
                        start_incidence = block_id.final_start_date
                        end_incidence = block_id.final_end_date

            incidence_id = self.env['attendance.incidence'].create({'check_in': start_incidence,
                                                                    'check_out': end_incidence,
                                                                    'employee_id': employee_id.id,
                                                                    'name': self.description,
                                                                    'productivity_block': True,
                                                                    'approve': False,
                                                                    'type_incidence': self.type_incidence})

            action = {
                'type': 'ir.actions.act_window',
                'views': [(False, 'tree')],
                'view_mode': 'form',
                'name': 'Leaves',
                'res_model': 'attendance.incidence',
                'target': 'current',
                'domain': [('id', '=', incidence_id.id)]
            }
            return action




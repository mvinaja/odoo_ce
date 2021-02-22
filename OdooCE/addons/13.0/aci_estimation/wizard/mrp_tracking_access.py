from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from odoo.http import request


class MrpTrackingBaseline(models.TransientModel):
    _name = 'mrp.tracking.access'
    _description = 'mrp.tracking.access'

    tracking_by = fields.Selection([('step', 'Step'), ('workorder', 'Workorder')])
    tracking_method = fields.Selection([('periodic', 'Periodic'), ('building', 'Building')])
    tracking_is_active = fields.Boolean(default=False)
    workcenter_id = fields.Many2one('mrp.workcenter')
    on_estimation = fields.Boolean(related='workcenter_id.on_estimation')
    baseline_id = fields.Many2one('lbm.baseline')
    period_id = fields.Many2one('payment.period')
    access_key = fields.Char('Access Key')

    def access_key_btn(self):
        self.ensure_one()
        workcenter_id = self.validate_key(self.workcenter_id, self.access_key)
        if not workcenter_id:
            raise ValidationError("Invalid Key")
        self.env['mrp.timetracking'].build_redirect_action(self.tracking_by, workcenter_id, self.tracking_method,
                                                           self.tracking_is_active,
                                                           self.baseline_id.id if self.baseline_id else None,
                                                           self.period_id.id if self.period_id else None)

    def get_supervised(self, workcenter_id):
        if workcenter_id:
            MrpWorkcenter = self.env['mrp.workcenter']
            workcenter_id = MrpWorkcenter.browse(workcenter_id)
            # Workcenters with the same employee
            workcenter_ids = MrpWorkcenter.search([('contract_id', '=', workcenter_id.contract_id.id)]).ids
            # Workcenters supervised by the employee (with one is enough since all have the same record)
            supervised_ids = self.env['mrp.production']. \
                search([('supervisor_ids', 'in', workcenter_id.employee_id.id)]).workorder_ids.mapped('resource_id').ids
            # Merge the two workcenter lists
            workcenter_ids = list(set(workcenter_ids + supervised_ids))
            # workcenter_name = workcenter_id.employee_id.name if workcenter_id.employee_id.name else workcenter_id.name
            # Get all the workcenters that are on estimation workcenter or are employees supervised by the main workcenter
            # employee
            workcenter_ids = self.env['mrp.estimation.workcenter'].search(['|',
                                                                          ('employee_id', 'in', workcenter_id.
                                                                          employee_id.child_ids.ids),
                                                                          ('workcenter_id', 'in', workcenter_ids)]).\
                mapped('workcenter_id').ids
            # Remove workcenters that doesn't have time records (could be by tracking or by estimation)
            workcenter_ids = self.env['mrp.timetracking.workorder'].search([('workcenter_id', 'in', workcenter_ids)]).\
                mapped('workcenter_id')
            # Create a dictionary that could be used on filters
            workcenter_data = list([wc.id, wc.employee_id.name if wc.employee_id else '',
                                    wc.employee_id.department_id.name if wc.employee_id.department_id else ''
                                   if wc.employee_id.name else wc.code] for wc in workcenter_ids)
            workcenter_data.sort(key=lambda x: (x[2], x[1]))
            return workcenter_ids.ids, workcenter_ids
        else:
            return [], None

    def validate_key(self, workcenter_id, access_key):
        if not access_key or not workcenter_id:
            return False

        real_key = workcenter_id.employee_id.tracking_password
        if not real_key or real_key != access_key or real_key == '':
            return False
        return workcenter_id

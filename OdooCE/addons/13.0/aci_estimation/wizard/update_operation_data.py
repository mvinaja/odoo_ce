# -*- coding: utf-8 -*-

from odoo import models, fields, api, exceptions, _


class UpdateWorkorderWizard(models.TransientModel):
    _name = 'update.workorder.wizard'
    _description = 'update.workorder.wizard'

    def update_data_btn(self):
        Workorder = self.env['mrp.workorder']
        LbmPeriod = self.env['lbm.period']
        Tworkorder = self.env['mrp.timetracking.workorder']
        for workorder in Workorder.browse(self.env.context.get('active_ids')):
            context_bom = workorder.production_id.context_bom
            operation = workorder.operation_id.with_context(default_context_bom=context_bom.id)
            values = {
                'operation_time': operation.duration / 60.0,
                'labor_cost': operation.operation_labor,
                'operation_labor': operation.operation_labor,
                'operation_fasar': operation.operation_fasar,
                'quality_restriction': operation.product_tmpl_id.quality_restriction,
            }
            if not workorder.manual_update:
                values['direct_cost'] = operation.operation_amount
                values['operation_extra'] = operation.operation_extra

            workorder.write(values)
            for step in workorder.step_ids:
                bom_line = step.workstep_id.with_context(default_context_bom=context_bom.id)
                step.write({
                    'manual_labor': bom_line.manual_labor,
                    'unit_labor': bom_line.unit_labor,
                    'unit_extra': bom_line.unit_extra,
                    'pay_amount': bom_line.pay_amount,
                    'labor_cost': bom_line.labor_cost,
                    'extra_cost': bom_line.extra_cost,
                })
            workorder.confirm_workstep()
            for tworkorder_id in Tworkorder.search([('workorder_id', '=', workorder.id)]):
                lbm_period_id = LbmPeriod.search([('baseline_id', '=', tworkorder_id.baseline_id.id),
                                                  ('period_start', '<=', tworkorder_id.start_date),
                                                  ('period_end', '>=', tworkorder_id.start_date)])
                lbm_period_id.process_replanning_btn(workorder_id=tworkorder_id.workorder_id.id)



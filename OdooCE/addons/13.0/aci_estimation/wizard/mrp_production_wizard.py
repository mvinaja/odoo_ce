# -*- coding: utf-8 -*-

from odoo import models, api, fields


class MrpProductionWizard(models.TransientModel):
    _inherit = 'mrp.production.wizard'

    def update_production_btn(self):
        self.ensure_one()
        Workorder = self.env['mrp.workorder']
        if self.type == 'model':
            for production_id in self.target_productions:
                updated_ids = self.env['mrp.workorder']
                source_bom = production_id.bom_id
                production_id.write({
                    'type': source_bom.type,
                    'project_id': source_bom.project_id.id})
                for bom_line in source_bom.operation_ids:
                    bom_line = bom_line.with_context(default_context_bom=production_id.context_bom.id)
                    workorders = production_id.workorder_ids
                    workorders = workorders.filtered(lambda r: r.operation_id == bom_line.child_bom_id)

                    values = Workorder.get_production_data(bom_line)
                    if workorders:
                        workorders.write(values)
                        updated_ids += workorders
                    else:
                        # Create workorder
                        values['production_id'] = production_id.id
                        values['state'] = not production_id.workorder_ids and 'ready' or 'pending'
                        updated_ids += Workorder.create(values)

                removed_ids = production_id.workorder_ids - updated_ids
                removed_ids.filtered(lambda r: r.has_tracking is True).write({'timetracking_active': False})
                removed_ids.filtered(lambda r: r.has_tracking is True).step_ids.write({'timetracking_active': False})
                removed_ids.filtered(lambda r: r.has_tracking is True).prev_link_ids.unlink()
                removed_ids.filtered(lambda r: r.has_tracking is True).next_link_ids.unlink()
                removed_ids.filtered(lambda r: r.has_tracking is False).unlink()

                # Update gantt chart
                production_id.update_gantt()

        else:
            for workorder in self.target_workorders:
                workorder.write(Workorder.get_production_data(workorder.operation_line))

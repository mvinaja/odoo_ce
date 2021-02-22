# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError

class CompareBomWizard(models.TransientModel):
    _inherit = 'compare.bom.wizard'

    report_type = fields.Selection([('explosion', 'Explosion'),
                                    ('component', 'Components'),
                                    ('step', 'Steps')], default='explosion')

    def compare_btn(self):
        self.ensure_one()
        url = '/aci_mrp_plm/compare_bom?src_ctx={}&src_bom={}&tgt_ctx={}&tgt_bom={}&rep_type={}'
        return {
            'type': 'ir.actions.act_url',
            'url': url.format(self.source_context.id, self.source_bom.id, self.target_context.id, self.target_bom.id, self.report_type),
            'target': 'new'
        }


class UpdateOperationBomWizard(models.TransientModel):
    _name = 'update.operation.bom.wizard'
    _description = 'update.operation.bom.wizard'

    update_pay = fields.Boolean('Pay Amount', default=True)
    update_extra = fields.Boolean('Extra Amount', default=True)
    update_rate = fields.Boolean('Rates', default=True)
    source_bom_id = fields.Many2one('mrp.bom')
    source_warehouse = fields.Many2one(related='source_bom_id.context_warehouse')
    source_context = fields.Many2one(related='source_bom_id.context_bom')
    source_bom_type = fields.Selection(related='source_bom_id.bom_type')
    source_product_tmpl_id = fields.Many2one(related='source_bom_id.product_id.product_tmpl_id')
    target_warehouse = fields.Many2one('stock.warehouse')
    target_context = fields.Many2one('mrp.bom')
    target_model_bom_ids = fields.Many2many('mrp.bom', 'update_operation_model_bom_rel')
    target_workorder_bom_ids = fields.Many2many('mrp.bom', 'update_workorder_model_bom_rel')
    bom_lines = fields.Many2many('mrp.bom.line', string='Workorders')

    def update_btn(self):
        if self.source_bom_type == 'model':
            self.update_model()
        else:
            self.update_workorder()

    def update_workorder(self):
        BomContext = self.env['mrp.bom.context']
        company_id = self.env.user.company_id
        for tgt_bom_id in self.target_workorder_bom_ids:
            if self.target_context not in tgt_bom_id.parent_bom_ids:
                message = 'Current BoM does not belongs to budget "{}"'
                raise UserError(_(message.format(self.target_context.name)))

            data = tgt_bom_id.context_price_ids
            data = data.filtered(
                lambda r: r.company_id == company_id and r.context_bom == self.target_context)
            if not data:
                data = BomContext.create({
                    'company_id': company_id.id,
                    'context_bom': self.target_context.id,
                    'bom_id': tgt_bom_id.id
                })

            if self.update_pay:
                data.operation_amount = self.source_bom_id.operation_amount
            if self.update_extra:
                data.operation_extra = self.source_bom_id.operation_extra
            if self.update_rate:
                for step in self.source_bom_id.workstep_ids:
                    target_step = tgt_bom_id.workstep_ids.filtered(
                        lambda r: r.product_id.id == step.product_id.id)
                    if target_step:
                        target_step.rate = step.rate

    def update_model(self):
        BomContext = self.env['mrp.bom.context']
        company_id = self.env.user.company_id
        for bom_line_id in self.bom_lines:
            product_tmpl_id = bom_line_id.product_id.product_tmpl_id.id
            for target_bom in self.target_model_bom_ids:
                tgt_workorder = target_bom.material_ids.filtered(lambda r: r.type == 'material' and
                                                                r.product_id.product_tmpl_id.id == product_tmpl_id)

                if tgt_workorder:
                    tgt_bom_id = tgt_workorder.child_bom_id
                    if self.target_context not in tgt_bom_id.parent_bom_ids:
                        message = 'Current BoM does not belongs to budget "{}"'
                        raise UserError(_(message.format(self.target_context.name)))

                    data = tgt_bom_id.context_price_ids
                    data = data.filtered(
                        lambda r: r.company_id == company_id and r.context_bom == self.target_context)
                    if not data:
                        data = BomContext.create({
                            'company_id': company_id.id,
                            'context_bom': self.target_context.id,
                            'bom_id': tgt_bom_id.id
                        })

                    if self.update_pay:
                        data.operation_amount = bom_line_id.child_bom_id.operation_amount
                    if self.update_extra:
                        data.operation_extra = bom_line_id.child_bom_id.operation_extra
                    if self.update_rate:
                        for step in bom_line_id.child_bom_id.workstep_ids:
                            target_step = tgt_bom_id.workstep_ids.filtered(lambda r: r.product_id.id == step.product_id.id)
                            if target_step:
                                target_step.rate = step.rate

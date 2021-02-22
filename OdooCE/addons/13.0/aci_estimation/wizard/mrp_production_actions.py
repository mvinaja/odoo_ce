# -*- coding: utf-8 -*-

from odoo import models, api, fields
from odoo.exceptions import ValidationError


class AciMrpProductionOperation(models.TransientModel):
    _name = 'mrp.production.actions'
    _description = 'mrp.production.actions'

    employee_id = fields.Many2one('hr.employee')

    def cancel_manufacturing(self):
        self.ensure_one()
        Production = self.env['mrp.production']
        ctx = self.env.context
        production_ids = Production.browse(ctx.get('active_ids'))
        production_ids.action_cancel()
        production_ids.unlink()

    def reset_time_tracking(self):
        self.ensure_one()
        ModelData = self.env['ir.model.data']
        Production = self.env['mrp.production']
        ctx = self.env.context
        production_ids = Production.browse(ctx.get('active_ids'))
        workorder_ids = production_ids.mapped('workorder_ids')
        wo_tracking_ids = workorder_ids.mapped('time_ids')
        step_ids = workorder_ids.mapped('step_ids')
        step_tracking_ids = step_ids.mapped('tracking_ids')
        stage_stop = ModelData.get_object(
            'aci_estimation', 'aci_stop_stage')

        wo_tracking_ids.unlink()
        step_tracking_ids.unlink()

        step_ids.write({
            'stage_id': stage_stop.id
        })

        workorder_ids.write({
            'date_start': False,
            'date_finished': False,
            'state': 'pending',
            'stage_id': stage_stop.id
        })

        production_ids.write({
            'date_start': False,
            'date_finished': False,
            'state': 'planned'
        })

    def add_supervisor(self):
        if not self.env.user.has_group('aci_estimation.group_estimation_chief'):
            raise ValidationError('You are not allowed to do this process')
        context = self.env.context
        active_ids = context.get('active_ids')
        production_ids = self.env['mrp.production'].browse(active_ids)
        production_ids.supervisor_ids = [(4, self.employee_id.id, False)]


class AciProductTemplateTargetOperation(models.TransientModel):
    _name = 'product.template.target.actions'
    _description = 'product.template.target.actions'

    action_id = fields.Many2one('product.template.actions')
    source_tmpl = fields.Many2one('product.template')
    source = fields.Many2one('product.product')
    target_tmpl = fields.Many2one('product.template')
    target = fields.Many2one('product.product')


class AciProductTemplateOperation(models.TransientModel):
    _name = 'product.template.actions'
    _description = 'product.template.actions'

    action = fields.Selection([('append', 'Append'),
                               ('remove', 'Remove'),
                               ('replace', 'Replace')], default='append')
    source_ids = fields.Many2many('product.product', string='Source')
    source_target_ids = fields.One2many('product.template.target.actions', 'action_id', string='Target')
    product_tmpl_ids = fields.Many2many('product.template')

    @api.model
    def default_get(self, fields):
        res = super(AciProductTemplateOperation, self).default_get(fields)
        product_id = self._context.get('product_id', None)
        context = self.env.context
        _ids = context.get('active_ids')
        model = context.get('source_res_model')
        field_name = context.get('source_res_field')
        if _ids and model == 'mrp.workorder':
            res['product_tmpl_ids'] = [(6, 0, self.env[model].browse(_ids).mapped(field_name).mapped('product_tmpl_id').ids)]
        elif product_id:
            res['product_tmpl_ids'] = [(6, 0, [product_id])]
        return res

    def append_value_btn(self):
        for product in self.product_tmpl_ids:
            product.quality_restriction_ids = [(0, False, {'product_id': pro.id,
                                                           'product_tmpl_rest_id': pro.product_tmpl_id.id}) for pro in self.source_ids if pro not in product.quality_restriction_ids.mapped('product_id')]

    def remove_value_btn(self):
        for product in self.product_tmpl_ids:
            product.quality_restriction_ids = [(3, product.quality_restriction_ids.filtered(lambda r: r.product_id.id == pro.id).id) for pro in self.source_ids if pro in product.quality_restriction_ids.mapped('product_id')]

    def replace_btn(self):
        for product in self.product_tmpl_ids:
            product.quality_restriction_ids = [(3, product.quality_restriction_ids.filtered(lambda r: r.product_id.id == pro.source.id).id) for pro in self.source_target_ids if pro.source in product.quality_restriction_ids.mapped('product_id')]
            product.quality_restriction_ids = [(0, False, {'product_id': pro.target.id,
                                                           'product_tmpl_rest_id': pro.target_tmpl.id}) for pro in self.source_target_ids if pro.target not in product.quality_restriction_ids.mapped('product_id')]

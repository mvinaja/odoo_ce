# -*- coding: utf-8 -*-

from odoo import models, api, fields, _


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    productivity_type = fields.Selection([
        ('productive', 'Productive'),
        ('improductive', 'Improductive'),
        ('supervise', 'Superviser')
    ], default='productive')
    quality_restriction = fields.Boolean()
    quality_restriction_ids = fields.One2many('product.template.quality', 'product_tmpl_id', string='Quality Restrictions')
    quality_restriction_qty = fields.Integer(compute='_compute_quality_restriction_qty')
    is_quality_control = fields.Boolean(compute='_compute_quality_control', store=True)

    @api.depends('product_variant_ids.is_quality_control')
    def _compute_quality_control(self):
        for r in self:
            r.is_quality_control = True if r.product_variant_ids.filtered(lambda y: y.is_quality_control is True) else False

    @api.depends('quality_restriction_ids')
    def _compute_quality_restriction_qty(self):
        for r in self:
            r.quality_restriction_qty = len(r.quality_restriction_ids)

    def action_see_quality_restriction(self):
        view_id = self.env['ir.model.data'].get_object(
            'aci_estimation', 'product_template_quality_tree_view')
        form_view_id = self.env['ir.model.data'].get_object(
            'aci_estimation', 'product_template_quality_form_view')
        return {
            'type': 'ir.actions.act_window',
            'views': [(view_id.id, 'tree'), (form_view_id.id, 'form')],
            'res_model': 'product.template.quality',
            'name': 'Quality Restrictions',
            'target': 'current',
            'domain': [('product_tmpl_id', '=', self.id)],
            'context': {'default_product_tmpl_id': self.id}
        }

    def quality_configurator_btn(self):
        view_id = self.env['ir.model.data'].get_object(
            'aci_estimation', 'product_template_actions_form_view')
        return {
            'type': 'ir.actions.act_window',
            'name': 'Quality Restriction Configurator',
            'views': [(view_id.id, 'form')],
            'res_model': 'product.template.actions',
            'target': 'new',
            'context': {'product_id': self.id}
        }

class ProductTemplateQuality(models.Model):
    _name = 'product.template.quality'
    _description = 'Product Template Quality Restrictions'
    _rec_name = 'product_id'

    product_tmpl_id = fields.Many2one('product.template', 'Source Template')
    product_tmpl_rest_id = fields.Many2one('product.template', string='Restriction Template', required=True, ondelete='restrict')
    product_id = fields.Many2one('product.product', 'Restriction Product', required=True, ondelete='restrict')

    @api.onchange('product_tmpl_rest_id')
    def onchange_product_tmpl_rest_id(self):
        return {'domain': {'product_id': [('product_tmpl_id', '=', self.product_tmpl_rest_id.id)]}}
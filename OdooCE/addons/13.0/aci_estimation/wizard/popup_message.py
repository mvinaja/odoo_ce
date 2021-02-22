# -*- coding: utf-8 -*-

from odoo import models, fields

class PopupMessage(models.TransientModel):
    _name = 'popup.message'
    _description = 'popup.message'

    message = fields.Text('Message', required=True)
    res_id = fields.Integer()
    error_log_ids = fields.One2many('popup.baseline.log.error', 'message_id', string='Error Logs')
    warning_log_ids = fields.One2many('popup.baseline.log.warning', 'message_id', string='Warning Logs')

    def done_btn(self):
        return {'type': 'ir.actions.act_window_close'}

class PopupBaselineLogError(models.TransientModel):
    _name = 'popup.baseline.log.error'
    _description = 'popup.baseline.log.error'

    state = fields.Selection([('period_group', 'Period Group'),
                              ('contract', 'Contract'),
                              ('analytic', 'Analytic Account'),
                              ('analytic_production', 'Analytic Mo')])
    message_id = fields.Many2one('popup.message')
    baseline_id = fields.Many2one('lbm.baseline', ondelete='cascade')
    product_id = fields.Many2one('product.product', string='Product Variant', ondelete='cascade')
    workorder_id = fields.Many2one('mrp.workorder', ondelete='cascade')
    production_id = fields.Many2one('mrp.production', ondelete='cascade')
    workcenter_id = fields.Many2one('mrp.workcenter', ondelete='cascade')
    contract_id = fields.Many2one(related='workcenter_id.contract_id')
    employee_id = fields.Many2one(related='workcenter_id.employee_id')

class PopupBaselineLogWarning(models.TransientModel):
    _name = 'popup.baseline.log.warning'
    _description = 'popup.baseline.log.warning'

    state = fields.Selection([('product', 'Product not configurated'),
                              ('duration', 'Planned Dates not inside Calendar'),
                              ('contract', 'Workcenter without Contract')])
    message_id = fields.Many2one('popup.message')
    baseline_id = fields.Many2one('lbm.baseline', ondelete='cascade')
    product_id = fields.Many2one('product.product', string='Product Variant', ondelete='cascade')
    workorder_id = fields.Many2one('mrp.workorder', ondelete='cascade')
    workcenter_id = fields.Many2one('mrp.workcenter', ondelete='cascade')
    contract_id = fields.Many2one(related='workcenter_id.contract_id')
    employee_id = fields.Many2one(related='workcenter_id.employee_id')

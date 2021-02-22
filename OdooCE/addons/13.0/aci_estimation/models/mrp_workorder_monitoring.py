# -*- coding: utf-8 -*-

from odoo import models, fields, api, tools, _


class MrpWorkorderMonitoring(models.Model):
    _name = 'mrp.workorder.monitoring'
    _description = 'mrp.workorder.monitoring'
    _auto = False
    _rec_name = 'product_id'
    _order = 'product_id'

    period_id = fields.Many2one('payment.period')
    party_id = fields.Many2one('product.product')
    analytic_id = fields.Many2one('account.analytic.account')
    product_id = fields.Many2one('product.product')
    product_tmpl_id = fields.Many2one('product.template')
    workcenter_id = fields.Many2one('mrp.workcenter')
    planned_progress = fields.Float()
    progress = fields.Float()
    on_estimation = fields.Integer()

    @api.model
    def init(self):
        cr = self.env.cr
        tools.sql.drop_view_if_exists(cr, 'mrp_workorder_monitoring')
        cr.execute("""
            CREATE OR REPLACE VIEW mrp_workorder_monitoring AS
            SELECT  row_number() OVER (ORDER BY wo.product_wo, analytic.id) AS id,
            lbm.period_id, party.id as party_id, analytic.id as analytic_id, wo.product_wo as product_id, 
            pt.id as product_tmpl_id,
            COALESCE(produc.resource_id, wo.resource_id) as workcenter_id,
            ite.ite_progress as planned_progress,
            COALESCE(COALESCE(produc.wo_qty_progress, 0.0) * 100 / wo.product_qty, 0.0) as progress,
            CAST(CASE WHEN est.id > 0 THEN 100 ELSE 0 END AS INTEGER) AS on_estimation
            FROM lbm_period lbm
            LEFT JOIN mrp_timetracking_workorder ite ON ite.ite_period_id = lbm.period_id
            LEFT JOIN account_analytic_account analytic ON analytic.id = ite.analytic_id
            LEFT JOIN mrp_workorder wo ON wo.id = ite.workorder_id
            LEFT JOIN product_product pro ON pro.id = wo.product_wo
            LEFT JOIN product_template pt ON pt.id = pro.product_tmpl_id
            LEFT JOIN product_product party ON party.id = pro.party_id
            LEFT JOIN mrp_workcenter_productivity produc ON produc.period_id = lbm.period_id
            AND wo.product_wo = produc.product_id AND analytic.id = produc.analytic_id
            LEFT JOIN mrp_estimation est ON est.workcenter_id = COALESCE(produc.resource_id, wo.resource_id) 
            AND est.period_id = ite.ite_period_id AND est.estimation_type = 'period'
""")

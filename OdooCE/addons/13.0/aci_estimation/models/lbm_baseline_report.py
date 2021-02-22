# -*- coding: utf-8 -*-

from odoo import models, api, fields, _


class lbmBaselineReport(models.Model):
    _name = 'lbm.baseline.report'
    _description = 'lbm.baseline.report'
    _auto = False

    sequence = fields.Integer(readonly=True)
    name = fields.Char(readonly=True)
    baseline_id = fields.Many2one('lbm.baseline', 'Baseline', readonly=True)
    date_start = fields.Datetime(readonly=True)
    date_end = fields.Datetime(readonly=True)
    planning_type = fields.Selection([('optimal', 'Optimal'), ('real', 'Real'),
                                      ('executed', 'Executed'), ('replanning', 'Replanning')], readonly=True)

    @api.model
    def init(self):
        cr = self.env.cr
        cr.execute("""
                CREATE OR REPLACE VIEW lbm_baseline_report AS
                WITH optimal AS (
                    SELECT lbm_wo.sequence, lbm_wo.name, lbm_sc.baseline_id, lbm_wo.date_start, lbm_wo.date_end, lbm_sc.planning_type    
                    FROM lbm_workorder lbm_wo 
                    INNER JOIN lbm_budget lbm_bd ON lbm_bd.id  = lbm_wo.lbm_budget_id
                    INNER JOIN lbm_scenario lbm_sc ON lbm_sc.id = lbm_bd.scenario_id
                    WHERE lbm_sc.planning_type = 'optimal'),
                    
                    sc_real AS (
                    SELECT lbm_wo.sequence, lbm_wo.name, lbm_sc.baseline_id, lbm_wo.date_start, lbm_wo.date_end, lbm_sc.planning_type      
                    FROM lbm_workorder lbm_wo 
                    INNER JOIN lbm_budget lbm_bd ON lbm_bd.id  = lbm_wo.lbm_budget_id
                    INNER JOIN lbm_scenario lbm_sc ON lbm_sc.id = lbm_bd.scenario_id
                    WHERE lbm_sc.planning_type = 'real'),
                    
                    executed AS (
                    SELECT lbm_wo.sequence, lbm_wo.name, lbm_sc.baseline_id, lbm_wo.date_start, lbm_wo.date_end, lbm_sc.planning_type       
                    FROM lbm_workorder lbm_wo 
                    INNER JOIN lbm_budget lbm_bd ON lbm_bd.id  = lbm_wo.lbm_budget_id
                    INNER JOIN lbm_scenario lbm_sc ON lbm_sc.id = lbm_bd.scenario_id
                    WHERE lbm_sc.planning_type = 'executed' and lbm_wo.render is True),
                    
                    replanning AS (
                    SELECT lbm_wo.sequence, lbm_wo.name, lbm_sc.baseline_id, lbm_wo.date_start, lbm_wo.date_end, lbm_sc.planning_type      
                    FROM lbm_workorder lbm_wo 
                    INNER JOIN lbm_budget lbm_bd ON lbm_bd.id  = lbm_wo.lbm_budget_id
                    INNER JOIN lbm_scenario lbm_sc ON lbm_sc.id = lbm_bd.scenario_id
                    WHERE lbm_sc.planning_type = 'replanning' and lbm_wo.render is True),

                    merged_table AS (SELECT * FROM optimal
                    UNION ALL SELECT * FROM sc_real
                    UNION ALL SELECT * FROM executed
                    UNION ALL SELECT * FROM replanning)

                    SELECT row_number() OVER (ORDER BY baseline_id, sequence, name) AS id,
			        sequence, name, baseline_id, date_start, date_end, planning_type FROM merged_table
    """)

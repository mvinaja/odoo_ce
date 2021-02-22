# -*- coding: utf-8 -*-

from odoo import models, api, fields
from odoo.http import request
from odoo.exceptions import ValidationError
import datetime

class MrpTimetrackingActivity(models.TransientModel):
    _name = 'mrp.timetracking.activity.wizard'
    _description = 'mrp.timetracking.activity.wizard'

    workcenter_ids = fields.One2many('mrp.timetracking.activity.workcen.wizard', 'activity_id')

    start_date = fields.Datetime('Start Date')
    end_date = fields.Datetime('End Date')

    @api.model
    def default_get(self, fields):
        res = super(MrpTimetrackingActivity, self).default_get(fields)
        context = self.env.context
        Config = self.env['mrp.estimation.workcenter']
        Workcen = self.env['mrp.timetracking.activity.workcen.wizard']
        workcenter_ids = Config.browse(context.get('active_ids'))
        res_ids = []
        for wc in workcenter_ids:
            _id = Workcen.create({'workcenter_id': wc.workcenter_id.id})
            res_ids.append(_id.id)
        res['workcenter_ids'] = res_ids
        return res

    def create_activity_block(self):
        if self.end_date <= self.start_date or not self.end_date or not self.start_date:
            raise ValidationError("The End Date must be bigger than Start Date")
        for workcenter_id in self.workcenter_ids.mapped('workcenter_id'):
            self.env['hr.productivity.block'].generate_specific_block(self.start_date, self.end_date, workcenter_id.employee_id)

class MrpTimetrackingWorkcenActivity(models.TransientModel):
    _name = 'mrp.timetracking.activity.workcen.wizard'
    _description = 'mrp.timetracking.activity.workcen.wizard'
    _rec_name = 'workcenter_id'

    activity_id = fields.Many2one('mrp.timetracking.activity.wizard')
    workcenter_id = fields.Many2one('mrp.workcenter')

class MrpTimetrackingWorkcenter(models.TransientModel):
    _name = 'mrp.timetracking.workcenter.wizard'
    _description = 'mrp.timetracking.workcenter.wizard'

    option = fields.Char(string='Change')
    option_workcenter = fields.Boolean('Workcenter', default=True)
    option_period = fields.Boolean('Period')
    option_estimation = fields.Boolean('Can Estimate', default=True)
    source = fields.Selection([('selection', 'Selection'),
                               ('all', 'All')], default='all', string='Partitions')
    estimated = fields.Selection([('can', 'Estimate'),
                                  ('not', 'No estimate')], default='can', string='Estimation')
    workcenter_id = fields.Many2one('mrp.workcenter')
    planned_workcenter = fields.Boolean(string='Use BL Workcenter')
    period_id = fields.Many2one('payment.period')
    period_ids = fields.Many2many('payment.period')
    lbm_period_id = fields.Many2one('lbm.period')
    baseline_id = fields.Many2one('lbm.baseline')

    @api.model
    def default_get(self, fields):
        res = super(MrpTimetrackingWorkcenter, self).default_get(fields)
        context = self.env.context
        ITE = self.env['mrp.timetracking.workorder']
        Timetracking = self.env['mrp.timetracking']
        model = context.get('model')
        if model == 'mrp.timetracking':
            _ids = []
            for timetracking_id in Timetracking.browse(context.get('active_ids')):
                ite_id = ITE.search([('baseline_id', '=', timetracking_id.baseline_id.id),
                                     ('end_date', '>=', timetracking_id.date_start),
                                     ('start_date', '<=', timetracking_id.date_start),
                                     ('workorder_id', '=', timetracking_id.workorder_id.id)])
                if ite_id:
                    _ids.append(ite_id.id)
            ite_ids = ITE.browse(_ids).filtered(lambda r: r.replanning_progress > 0)
        else:
            ite_ids = ITE.browse(context.get('active_ids')).filtered(lambda r: r.replanning_progress > 0)

        if not ite_ids:
            raise ValidationError('Select at least one valid ITE record')
        lbm_period_id = self.env['lbm.period'].search([('baseline_id', '=', ite_ids[0].workorder_id.baseline_id.id),
                                                       ('period_start', '<=', ite_ids[0].start_date),
                                                       ('period_end', '>=', ite_ids[0].start_date)])
        res['lbm_period_id'] = lbm_period_id.id
        lbm_period_ids = self.env['lbm.period'].search([('baseline_id', '=', ite_ids[0].workorder_id.baseline_id.id),
                                                        ('period_group', '=', ite_ids[0].ite_period_id.group_id.id),
                                                        ('id', '!=', lbm_period_id.id)])
        res['period_ids'] = [(6, 0, lbm_period_ids.mapped('period_id').ids)]
        return res

    def change_btn(self):
        context = self.env.context
        ITE = self.env['mrp.timetracking.workorder']
        Timetracking = self.env['mrp.timetracking']
        model = context.get('model')
        if model == 'mrp.timetracking':
            _ids = []
            for timetracking_id in Timetracking.browse(context.get('active_ids')):
                ite_id = ITE.search([('baseline_id', '=', timetracking_id.baseline_id.id),
                                     ('end_date', '>=', timetracking_id.date_start),
                                     ('start_date', '<=', timetracking_id.date_start),
                                     ('workorder_id', '=', timetracking_id.workorder_id.id)])
                if ite_id:
                    _ids.append(ite_id.id)
            tworkorder_ids = ITE.browse(_ids).filtered(lambda r: r.replanning_progress > 0)
        else:
            tworkorder_ids = ITE.browse(context.get('active_ids')).filtered(lambda r: r.replanning_progress > 0)

        if self.source == 'all':
            tworkorder_ids = ITE.search([('workorder_id', 'in', tworkorder_ids.mapped('workorder_id').ids)]).\
                filtered(lambda r: r.replanning_qty_progress > 0)
        if self.option_estimation:
            tworkorder_ids.write({'can_be_estimated': True if self.estimated == 'can' else False})
        if self.option_workcenter:
            if not self.planned_workcenter:
                tworkorder_ids.write({'workcenter_id': self.workcenter_id.id})
            else:
                for tworkorder_id in tworkorder_ids:
                    tworkorder_id.write({'workcenter_id': tworkorder_id.planned_workcenter_id.id})
        if self.option_period:
            lbm_period_id = self.env['lbm.period'].search([('baseline_id', '=', tworkorder_ids[0].workorder_id.baseline_id.id),
                                                           ('period_id', '=', self.period_id.id)])
            lbm_period_id.move_ite_btn()

        # ToDo. Improve
        if not self.option_period:
            for tworkorder_id in tworkorder_ids:
                lbm_period_id = self.env['lbm.period'].search([('baseline_id', '=', tworkorder_id.baseline_id.id),
                                                               ('period_start', '<=', tworkorder_id.start_date),
                                                               ('period_end', '>=', tworkorder_id.start_date)])
                for tw in ITE.search([('baseline_id', '=', tworkorder_id.baseline_id.id),
                                    ('end_date', '>=', tworkorder_id.start_date),
                                    ('start_date', '<=', tworkorder_id.start_date),
                                    ('workcenter_id', '=', tworkorder_id.workcenter_id.id)]):
                    lbm_period_id.process_replanning_btn(workorder_id=tw.workorder_id.id)

# Remove
class MrpTimetrackingWorkcenWorkcenter(models.TransientModel):
    _name = 'mrp.timetracking.workcenter.workcen.wizard'
    _description = 'mrp.timetracking.workcenter.workcen.wizard'
    _rec_name = 'workcenter_id'

    activity_id = fields.Many2one('mrp.timetracking.workcenter.wizard')
    workcenter_id = fields.Many2one('mrp.workcenter')
    new_workcenter_id = fields.Many2one('mrp.workcenter')
    employee_id = fields.Many2one(related='new_workcenter_id.employee_id')
    period_group_id = fields.Many2one(related='new_workcenter_id.period_group_id')
    contract_id = fields.Many2one(related='new_workcenter_id.contract_id')
    resource_calendar_id = fields.Many2one(related='new_workcenter_id.resource_calendar_id')

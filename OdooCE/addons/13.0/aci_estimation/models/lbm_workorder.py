# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from datetime import datetime, timedelta
import random
from odoo.exceptions import UserError


class LbmWorkorder(models.Model):
    _inherit = 'lbm.workorder'

    render = fields.Boolean(default=True)
    analytic_id = fields.Many2one(related='production_id.project_id', string='Analytic')
    can_be_planned = fields.Boolean(string='Can be planned', related='workorder_id.can_be_planned')
    delayed = fields.Boolean(compute='_compute_delayed')
    lookahead_active = fields.Boolean(compute='_compute_lookahead_active', store=True, string='In LookAHead')
    track_workstep = fields.Boolean(compute='_compute_track_workstep', store=True)
    use_restriction = fields.Boolean(related='workorder_id.use_restriction', string='Rest.Dom.')
    active_restriction_count = fields.Integer(related='workorder_id.active_restriction_count', string='Act.Rest')
    manage_type = fields.Selection(related='workorder_id.manage_type')
    timetracking_type = fields.Selection(related='workorder_id.timetracking_type')

    @api.depends('date_start', 'can_be_planned')
    def _compute_delayed(self):
        today = datetime.now()
        for r in self:
            r.delayed = True if r.date_start < today and not r.can_be_planned else False

    @api.depends('date_start')
    def _compute_lookahead_active(self):
        today = datetime.now().replace(hour=0, minute=0, second=0)
        start = today - timedelta(days=today.weekday())  # Go to Monday
        start_year = today.year
        for r in self:
            end_week = today.isocalendar()[1] + r.baseline_id.lookahead_window - 1
            week_factor = int(end_week / 52)
            end_week = end_week - (52 * week_factor)
            end_year = start_year + week_factor
            end = datetime.strptime('{}-W{}-0'.format(end_year, end_week), "%Y-W%W-%w")

            r.lookahead_active = True if start <= r.date_start <= end else False

    @api.depends('workorder_id.step_ids')
    def _compute_track_workstep(self):
        for r in self:
            r.track_workstep = True if r.workorder_id.step_ids else False

    def show_restriction_btn(self):
        _ids = self.env['mrp.workorder'].browse([self.workorder_id.id]).activity_ids.ids
        view_id = self.env['ir.model.data'].get_object(
            'aci_estimation', 'mail_activity_tree_view')
        return {
            'name': _('all activity'),
            'res_model': 'mail.activity',
            'type': 'ir.actions.act_window',
            'views': [(view_id.id, 'tree')],
            'target': 'current',
            'domain': [('id', 'in', _ids)],
            'context': self._context,
        }

    def show_workorder_btn(self):
        view_id = self.env['ir.model.data'].get_object(
            'mrp', 'mrp_production_workorder_form_view_inherit')
        return {
            'name': _('WorkOrder'),
            'res_model': 'mrp.workorder',
            'type': 'ir.actions.act_window',
            'views': [(view_id.id, 'form')],
            'target': 'current',
            'res_id': self.workorder_id.id
        }

    def change_can_be_planned(self, use_restriction):
        if not self.env.user.has_group('aci_estimation.group_estimation_manager'):
            raise UserError(_('You are not allowed to do this process'))
        context = self.env.context
        workorder_ids = self.browse(context.get('active_ids')).mapped('workorder_id')
        for workorder_id in workorder_ids:
            workorder_id.use_restriction = use_restriction

    def block_workorder_btn(self, context=None):
        self.change_can_be_planned(True)

    def open_workorder_btn(self, context=None):
        self.change_can_be_planned(False)

    def random_tracking_btn(self, context=None):
        context = self.env.context
        lbm_workorder_ids = self.browse(context.get('active_ids')).filtered(lambda r: r.track_workstep is True)
        for period_id in lbm_workorder_ids.mapped('period_id'):
            product_ids = lbm_workorder_ids.filtered(lambda r: r.period_id.id == period_id.id).mapped('product_id')
            for product_id in product_ids:
                workorder_ids = lbm_workorder_ids.filtered(lambda r: r.period_id.id == period_id.id and \
                                                          r.product_id.id == product_id.id).mapped('workorder_id')
                random.choice(workorder_ids).timetracking_type = 'mixed'

    def change_tracking_btn(self, context=None):
        context = self.env.context
        for lbm_workorder_id in self.browse(context.get('active_ids')):
            if lbm_workorder_id.manage_type == 'step' and lbm_workorder_id.timetracking_type == 'workorder':
                lbm_workorder_id.timetracking_type = 'mixed'
            elif lbm_workorder_id.manage_type == 'workorder' and lbm_workorder_id.timetracking_type == 'workorder':
                lbm_workorder_id.timetracking_type = 'workorder'
            elif lbm_workorder_id.manage_type == 'workorder' and lbm_workorder_id.timetracking_type == 'mixed':
                lbm_workorder_id.timetracking_type = 'workorder'
            elif lbm_workorder_id.timetracking_type == 'mixed':
                lbm_workorder_id.timetracking_type = 'workorder'
            else:
                lbm_workorder_id.timetracking_type = 'workorder'

# -*- coding: utf-8 -*-

from odoo import models, api, _, fields
from datetime import datetime, timedelta
from odoo.http import request


class LbmBaseline(models.Model):
    _inherit = 'lbm.baseline'

    lookahead_window = fields.Integer(compute='_compute_lookahead_window', string='LookAHead (weeks)')

    def unlink(self):
        self.ensure_one()
        ModelData = self.env['ir.model.data']

        workorder_ids = self.production_ids.mapped('workorder_ids')
        wo_tracking_ids = workorder_ids.mapped('time_ids')
        step_ids = workorder_ids.mapped('step_ids')
        step_tracking_ids = step_ids.mapped('tracking_ids')
        stage_stop = ModelData.get_object('aci_estimation', 'aci_stop_stage')

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
        return super(LbmBaseline, self).unlink()

    @api.depends('scenario_ids.period_ids')
    def _compute_lookahead_window(self):
        for r in self:
            scenario_id = r.scenario_ids.filtered(lambda y: y.planning_type == 'replanning')
            period_group_id = scenario_id.period_ids.mapped('period_group')[0] if scenario_id and \
                                                                                  scenario_id.period_ids.\
                                                                                      mapped('period_group') else None
            if period_group_id:
                current_period = period_group_id.period_ids.filtered(lambda _r: _r.from_date < datetime.now() <= _r.to_date)
            else:
                current_period = None

            period_ids = scenario_id.period_ids.filtered(
                lambda y: y.period_id.global_sequence > current_period.global_sequence) \
                if current_period else None
            r.lookahead_window = len(period_ids) if period_ids else 0

    def confirm_scenario_btn(self):
        super(LbmBaseline, self).confirm_scenario_btn()
        real_scenario_ids = self.scenario_ids.filtered(lambda r: r.planning_type == 'real' and r.id != self.planned_scenario.id)
        if real_scenario_ids and self.planned_scenario.planning_type == 'optimal':
            real_scenario_ids.unlink()
        if self.planned_scenario.planning_type == 'real':
            if not self.scenario_ids.filtered(lambda r: r.planning_type == 'executed'):
                self.planned_scenario.duplicate_scenario('executed')
            if not self.scenario_ids.filtered(lambda r: r.planning_type == 'replanning'):
                self.planned_scenario.duplicate_scenario('replanning')
        if self.planned_scenario.planning_type == 'optimal':
            self.planned_scenario.duplicate_scenario('real')

    def show_flowline_btn(self):
        gantt_view_id = self.env['ir.model.data'].get_object(
            'aci_estimation', 'lbm_baseline_report_gantt_view')
        return {
            'type': 'ir.actions.act_window',
            'name': 'Scenario Report',
            'views': [(gantt_view_id.id, 'gantt'), (False, 'tree')],
            'res_model': 'lbm.baseline.report',
            'domain': [('baseline_id', '=', self.id)],
            'target': 'current'
        }

    def action_supervisor(self):
        workcenter_ids = self.env['mrp.production']. \
            search([('id', 'in', self.production_ids.ids)]).workorder_ids.mapped('resource_id').ids
        est_workcenter_ids = self.env['mrp.estimation.workcenter'].search([('workcenter_id', 'in', workcenter_ids),
                                                                           ('is_supervisor', '=', True)])
        view_id = self.env['ir.model.data'].get_object(
            'aci_estimation', 'mrp_estimation_workcenter_baseline_tree_view')

        return {
            'type': 'ir.actions.act_window',
            'name': 'Supervisors',
            'views': [(view_id.id, 'tree')],
            'res_model': 'mrp.estimation.workcenter',
            'domain': [('id', 'in', est_workcenter_ids.ids)],
            'target': 'current'
        }

    def action_workcenter(self):
        workcenter_ids = self.env['mrp.production']. \
            search([('id', 'in', self.production_ids.ids)]).workorder_ids.mapped('resource_id').ids
        est_workcenter_ids = self.env['mrp.estimation.workcenter'].search([('workcenter_id', 'in', workcenter_ids)])
        view_id = self.env['ir.model.data'].get_object(
            'aci_estimation', 'mrp_estimation_workcenter_baseline_tree_view')
        return {
            'type': 'ir.actions.act_window',
            'name': 'Workcenters',
            'views': [(view_id.id, 'tree')],
            'res_model': 'mrp.estimation.workcenter',
            'domain': [('id', 'in', est_workcenter_ids.ids)],
            'target': 'current'
        }

    def action_tracking_approve(self):
        self.ensure_one()
        flowline_view = self.env['ir.model.data'].get_object(
            'aci_lbm_flowline', 'lbm_workorder_flowline_view')
        tree_view = self.env['ir.model.data'].get_object(
            'aci_estimation', 'lbm_workorder_tree_restriction_view')
        gantt_view = self.env['ir.model.data'].get_object(
            'aci_lbm_flowline', 'lbm_workorder_gantt_view')

        today = datetime.now().replace(hour=0, minute=0, second=0)
        start = today - timedelta(days=today.weekday())  # Go to Monday
        start_year = today.year

        end_week = today.isocalendar()[1] + self.lookahead_window - 1
        week_factor = int(end_week / 52)

        end_week = end_week - (52 * week_factor)
        end_year = start_year + week_factor
        end = datetime.strptime('{}-W{}-0'.format(end_year, end_week), "%Y-W%W-%w")

        scenario_id = self.scenario_ids.filtered(lambda r: r.planning_type == 'replanning')
        lbm_workorder_ids = self.env['lbm.workorder'].search([('scenario_id', '=', scenario_id.id),
                                                              ('date_start', '>=', start),
                                                              ('date_start', '<=', end)])

        return {
            'name': _('Flowline Chart'),
            'res_model': 'lbm.workorder',
            'views': [(flowline_view.id, 'flowline'), (gantt_view.id, 'aci_gantt'), (tree_view.id, 'tree')],
            'type': 'ir.actions.act_window',
            'domain': [('id', 'in', lbm_workorder_ids.ids)],
            'target': 'current'
        }

    def action_tracking(self):
        workcenter_ids = self.env['mrp.production']. \
            search([('id', 'in', self.production_ids.ids)]).workorder_ids.mapped('resource_id').ids
        tracking_ids = self.env['mrp.timetracking'].search([('workcenter_id', 'in', workcenter_ids),
                                                            ('baseline_id', '=', self.id)])
        view_id = self.env['ir.model.data'].get_object(
            'aci_estimation', 'mrp_timetracking_tree_view')
        calendar_view_id = self.env['ir.model.data'].get_object(
            'aci_estimation', 'mrp_timetracking_calendar_view')
        return {
            'type': 'ir.actions.act_window',
            'name': 'Activity',
            'views': [(view_id.id, 'tree'), (calendar_view_id.id, 'calendar')],
            'res_model': 'mrp.timetracking',
            'domain': [('id', 'in', tracking_ids.ids)],
            'target': 'current'
        }

    def delete_tracking_btn(self):
        timetracking_ids = self.env['mrp.timetracking'].search([('baseline_id', '=', self.id)])
        for prod_id in self.env['mrp.workcenter.productivity'].search([('timetracking_id', 'in', timetracking_ids.ids)]):
            prod_id.unlink()
        self.env['mrp.timetracking'].search([('baseline_id', '=', self.id)]).unlink()

    def set_period_btn(self):
        scenario_id = self.scenario_ids.filtered(lambda r: r.planning_type == 'replanning')

        view_id = self.env['ir.model.data'].get_object(
            'aci_lbm_flowline', 'lbm_period_tree_view')

        return {'type': 'ir.actions.act_window',
                'name': '{}'.format(self.name),
                'views': [(view_id.id, 'tree')],
                'res_model': 'lbm.period',
                'domain': [('scenario_id', '=', scenario_id.id)],
                'target': 'current',
                'context': {'default_group_ids': self.group_ids.ids,
                             'default_scenario_id': scenario_id.id}}

    def show_workcenter_btn(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Workcenters',
            'view_type': 'form',
            'view_mode': 'tree, form',
            'res_model': 'mrp.workcenter',
            'views': [[False, "tree"]],
            'domain': [('id', 'in', self.production_ids.workorder_ids.mapped('resource_id').ids)],
            'target': 'current',
        }

    # Estimation Buttons
    def show_period_estimation(self):
        context = self.env.context
        workcenter_ids = context.get('workcenter_ids') if context.get('workcenter_ids') else []

        view_id = self.env['ir.model.data'].get_object(
            'aci_estimation', 'mrp_estimation_tree_view')

        production_ids = self.env['mrp.production'].search([('baseline_id', '=', self.id)]).ids
        workorder_ids = self.env['mrp.workorder'].search([('production_id', 'in', production_ids)])
        wo_ids = workorder_ids.mapped('resource_id')
        step_ids = self.env['lbm.work.order.step'].search([('production_id', 'in', production_ids)]).mapped('wkcenter')

        input_wc_ids = self.env['mrp.workcenter.productivity'].search([('workorder_by_step', 'in', workorder_ids.ids)]).\
            mapped('resource_id')

        record_ids = wo_ids.ids + step_ids.ids
        _workcenter_ids = list(set(record_ids) & set(workcenter_ids))
        _workcenter_ids = _workcenter_ids + input_wc_ids.ids
        return {
            'type': 'ir.actions.act_window',
            'views': [(view_id.id, 'tree'), (False, 'form')],
            'view_mode': 'tree, form',
            'target': 'current',
            'name': _('Estimation'),
            'res_model': 'mrp.estimation',
            'domain': [('workcenter_id', 'in', _workcenter_ids)],
            'context': {'warehouse_id': self.id,
                        'search_default_filter_periodic_estimation': 1}
        }

    def show_restriction(self):
        return self.show_activity_type('restriction')

    def show_noncompliance(self):
        return self.show_activity_type('noncompliance')

    def show_nonconformity(self):
        return self.show_activity_type('nonconformity')

    def show_activity_type(self, activity_source):
        context = self.env.context
        workcenter_ids = context.get('workcenter_ids') if context.get('workcenter_ids') else []
        production_ids = self.env['mrp.production'].search([('baseline_id', '=', self.id)])
        activity_ids = []
        for activity in production_ids.mapped('workorder_ids').activity_ids.\
            filtered(lambda r: r.activity_source == activity_source):
            if self.env.user.has_group('aci_estimation.group_estimation_chief'):
                activity_ids.append(activity.id)
            elif list(set(activity.workcenter_ids) & set(workcenter_ids)):
                activity_ids.append(activity.id)

        view_id = self.env['ir.model.data'].get_object(
            'aci_estimation', 'mail_activity_tree_view')
        return {
            'name': _('Restrictions'),
            'res_model': 'mail.activity',
            'type': 'ir.actions.act_window',
            'views': [(view_id.id, 'tree')],
            'target': 'current',
            'domain': [('id', 'in', activity_ids)],
            'context': self._context,
        }

    def show_workcenter_estimation(self):
        context = self.env.context
        workcenter_ids = context.get('workcenter_ids') if context.get('workcenter_ids') else []
        parent_workcenter_id = context.get('parent_workcenter_id') if context.get('parent_workcenter_id') else None
        est_workcenter_ids = context.get('est_workcenter_ids') if context.get('est_workcenter_ids') else []
        view_id = self.env['ir.model.data'].get_object(
            'aci_estimation', 'mrp_estimation_workcenter_tree_view')
        production_ids = self.env['mrp.production'].search([('baseline_id', '=', self.id)]).ids
        wo_ids = self.env['mrp.workorder'].search([('production_id', 'in', production_ids)]).mapped('resource_id')
        step_ids = self.env['lbm.work.order.step'].search([('production_id', 'in', production_ids)]).mapped('wkcenter')
        record_ids = wo_ids.ids + step_ids.ids

        _ids = self.env['mrp.estimation.workcenter'].search([('workcenter_id', 'in', record_ids)]).ids
        _workcenter_ids = list(set(_ids) & set(est_workcenter_ids))
        action = {
            'type': 'ir.actions.act_window',
            'views': [(view_id.id, 'tree')],
            'view_mode': 'tree',
            'target': 'current',
            'name': _('Workcenter'),
            'res_model': 'mrp.estimation.workcenter',
            'domain': [('id', 'in', _workcenter_ids)],
            'context': {'search_default_filter_active_estimation': 1,
                        'workcenter_ids': workcenter_ids,
                        'parent_workcenter_id': parent_workcenter_id,
                        'warehouse_id': self.id}
        }
        return action

    def show_workorder_btn(self):
        Timetracking = self.env['mrp.timetracking']
        Workcenter = self.env['mrp.workcenter']
        if self.env.user.shared_account:
            if request.session.get('session_workcenter'):
                action = Timetracking.build_redirect_action(type='workorder',
                                                            workcenter_id=Workcenter.browse([request.session.
                                                                                            get('session_workcenter')]),
                                                            baseline_id=self.id)
            else:
                action = self.env.ref('aci_estimation.mrp_tracking_wo_action').read()[0]
                action['context'] = {'default_tracking_by': 'workorder',
                                     'default_tracking_method': 'building',
                                     'default_baseline_id': self.id}
        else:
            action = Timetracking.build_redirect_action(type='workorder', baseline_id=self.id)
        return action

    def show_step_btn(self):
        Timetracking = self.env['mrp.timetracking']
        Workcenter = self.env['mrp.workcenter']
        if self.env.user.shared_account:
            if request.session.get('session_workcenter'):
                action = Timetracking.build_redirect_action(type='workorder',
                                                            workcenter_id=Workcenter.browse([request.session.
                                                                                            get('session_workcenter')]),
                                                            baseline_id=self.id)
            else:
                action = self.env.ref('aci_estimation.mrp_tracking_wo_action').read()[0]
                action['context'] = {'default_tracking_by': 'step',
                                     'default_tracking_method': 'building',
                                     'default_baseline_id': self.id}
        else:
            action = Timetracking.build_redirect_action(type='step', baseline_id=self.id)
        return action

    def show_cost_btn(self):
        view_id = self.env['ir.model.data'].get_object(
            'aci_estimation', 'mrp_workcenter_productivity_timeline')
        view_tree_id = self.env['ir.model.data'].get_object(
            'aci_estimation', 'mrp_workcenter_productivity_estimation_cost_tree_view')
        view_pivot_id = self.env['ir.model.data'].get_object(
            'aci_estimation', 'mrp_workcenter_productivity_estimation_pivot_view')

        action = {
            'type': 'ir.actions.act_window',
            'views': [(view_tree_id.id, 'tree'),
                      (view_pivot_id.id, 'pivot'),
                      (view_id.id, 'timeline')],
            'view_mode': 'form,timeline',
            'name': 'Cost Report',
            'res_model': 'mrp.workcenter.productivity',
            'target': 'current',
            'clear_breadcrumbs': True,
            'domain': [('workorder_id', 'in', self.production_ids.workorder_ids.ids),
                       ('qty_status', '=', 'approved')],
            'context': {'group_by': ['period_id', 'employee_id', 'analytic_id', 'product_id'],
                        'default_search_current_period': True}
        }
        return action
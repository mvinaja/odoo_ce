# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from datetime import timedelta, datetime
from odoo.exceptions import ValidationError

class LbmScenario(models.Model):
    _inherit = 'lbm.scenario'

    planning_type = fields.Selection([('optimal', 'Optimal'), ('real', 'Real'),
                                      ('executed', 'Executed'), ('replanning', 'Replanning')], default='optimal')
    type_sequence = fields.Integer(compute='_compute_type_sequence', store=True)
    baseline_type = fields.Selection(related='baseline_id.type')


    @api.depends('planning_type')
    def _compute_type_sequence(self):
        for r in self:
            r.type_sequence = len(self.search([('planning_type', '=', r.planning_type)]).ids)

    def analyze_scenario(self):
        workorder_ids = self.baseline_id.production_ids.mapped('workorder_ids')
        missing = []
        dates = []
        for workorder_id in workorder_ids:
            lbm_workorder_id = self.lbm_workord_ids.filtered(lambda y: y.workorder_id.id == workorder_id.id)
            if not lbm_workorder_id:
                missing.append(workorder_id.product_wo.complete_name)
            elif lbm_workorder_id.date_start != workorder_id.date_planned_start or \
                    lbm_workorder_id.date_end != workorder_id.date_planned_finished:
                wo_start = self.env['time.tracking.actions'].get_tz_datetime(workorder_id.date_planned_start,
                                                                              self.env.user)
                wo_end = self.env['time.tracking.actions'].get_tz_datetime(workorder_id.date_planned_finished,
                                                                              self.env.user)
                planned_start = self.env['time.tracking.actions'].get_tz_datetime(lbm_workorder_id.date_start,
                                                                              self.env.user)
                planned_end = self.env['time.tracking.actions'].get_tz_datetime(lbm_workorder_id.date_end,
                                                                              self.env.user)
                dates.append('{} WorkOrder {} to {} and Planned in {} to {}'.format(workorder_id.product_wo.complete_name,
                                                                                    wo_start.strftime("%Y/%m/%d %H:%M"),
                                                                                    wo_end.strftime("%Y/%m/%d %H:%M"),
                                                                                    planned_start.strftime("%Y/%m/%d %H:%M"),
                                                                                    planned_end.strftime("%Y/%m/%d %H:%M")))
        if missing or dates:
            raise ValidationError(_('Missing Workorder:\n {}\n'
                                    'Dates: \n {}'.format('\n'.join(missing), dates[0])))
        raise ValidationError('No errors detected')

    def _generate_error_message(self, error_log, warning_log):
        pg_count = 0
        an_count = 0
        an_mo_count = 0
        production_list = []
        analytic_list = []
        period_group_list = []
        error_list = []
        for _error in error_log:
            if _error['state'] == 'period_group':
                if _error['workcenter_id'] not in period_group_list:
                    period_group_list.append(_error['workcenter_id'])
                    error_list.append({'state': 'period_group', 'product_id': None,
                                       'workorder_id': None,
                                       'production_id': None,
                                       'workcenter_id': _error['workcenter_id']})
                    pg_count += 1
            elif _error['state'] == 'analytic':
                if _error['workcenter_id'] not in analytic_list:
                    analytic_list.append(_error['workcenter_id'])
                    error_list.append({'state': 'analytic', 'product_id': None,
                                       'workorder_id': None,
                                       'production_id': None,
                                       'workcenter_id': _error['workcenter_id']})
                    an_count += 1
            elif _error['state'] == 'analytic_production':
                if _error['production_id'] not in production_list:
                    production_list.append(_error['production_id'])
                    error_list.append({'state': 'analytic_production', 'product_id': None,
                                       'workorder_id': None,
                                       'production_id': _error['production_id'],
                                       'workcenter_id': None})
                    an_mo_count += 1

        warning_log_ids = [(0, 0, {'state': l['state'],
                                   'product_id': l['product_id'],
                                   'workorder_id': l['workorder_id'],
                                   'workcenter_id': l['workcenter_id'],
                                   'baseline_id': self.baseline_id.id}) for l in warning_log]

        # Horrible Message PopUp, check for better solution
        error_log_ids = [(0, 0, {'state': l['state'],
                                 'product_id': l['product_id'],
                                 'workorder_id': l['workorder_id'],
                                 'production_id': l['production_id'],
                                 'workcenter_id': l['workcenter_id'],
                                 'baseline_id': self.baseline_id.id}) for l in error_list]

        return self.env['popup.message'].create({'res_id': self.baseline_id.id,
                                                 'error_log_ids': error_log_ids,
                                                 'warning_log_ids': warning_log_ids,
                                                 'message': 'Error on data:\n'
                                                            'Workcenters without PeriodGroup = {}\n' \
                                                            'Contract without Analytic Account = {}\n'\
                                                            'Manufacturing Orders without Analytic = {}\n'.
                                                            format(pg_count, an_count, an_mo_count)})

    def duplicate_scenario(self, type='replanning'):
        scenario_id = super(LbmScenario, self).copy()
        scenario_id.planning_type = type
        budget_ids = scenario_id.lbm_budget_ids

        # FIX ME
        for budget_id in budget_ids:
            for workord_id in budget_id.lbm_task_ids.lbm_workord_ids:
                scenario_id.lbm_workord_ids = [(4, workord_id.id)]
                workord_id.lbm_budget_id = budget_id.id
        # scenario_id.lbm_budget_ids.lbm_task_ids.lbm_rate_ids.filtered(lambda r: r.base_rate == 0).unlink()

        # Rebuilding links
        for workorder_id in self.lbm_workord_ids:
            budget_id = [budget.id for budget in budget_ids if budget.name == workorder_id.lbm_budget_id.name]
            prev_link_ids_dict = []
            prev_link_ids = self.env['lbm.workorder.link'].search([('current_id', '=', workorder_id.id)])
            for link in prev_link_ids:
                prev_link_ids_dict.append({'lag': link.lag, 'type': link.type,
                                           'current_id': self.get_new_lbm_workorder(link.current_id.id, budget_id[0]),
                                           'previous_id': self.get_new_lbm_workorder(link.previous_id.id, budget_id[0])})

            next_link_ids_dict = []
            next_link_ids = self.env['lbm.workorder.link'].search([('previous_id', '=', workorder_id.id)])
            for link in next_link_ids:
                next_link_ids_dict.append({'lag': link.lag, 'type': link.type,
                                           'current_id': self.get_new_lbm_workorder(link.current_id.id, budget_id[0]),
                                           'previous_id': self.get_new_lbm_workorder(link.previous_id.id, budget_id[0])})

            workorder_id.prev_link_ids = [[0, 0, link] for link in prev_link_ids_dict]
            workorder_id.next_link_ids = [[0, 0, link] for link in next_link_ids_dict]

    def get_new_lbm_workorder(self, lbm_workorder_id, budget_id):
        lbm_workorder_id = self.env['lbm.workorder'].browse([lbm_workorder_id])
        return self.env['lbm.workorder'].search([('name', '=', lbm_workorder_id.name),
                                                 ('production_id', '=', lbm_workorder_id.production_id.id),
                                                 ('lbm_budget_id', '=', budget_id),
                                                 ('id', '!=', lbm_workorder_id.id)]).id

    def validate_tracking(self, record_ids, analytic_ids, origin, baseline_type, error_log, warning_log):
        for record_id in record_ids:
            workorder_id = record_id
            production_id = record_id.production_id
            product_id = record_id.product_wo
            date_start = record_id.date_planned_start
            date_end = record_id.date_planned_finished
            workcenter_id = record_id.resource_id
            calendar_id = workcenter_id.resource_calendar_id
            contract_id = workcenter_id.contract_id
            period_group_id = workcenter_id.period_group_id.id if workcenter_id else None
            error_log_line = {'state': None, 'product_id': product_id.id,
                              'workorder_id': workorder_id.id,
                              'workcenter_id': workcenter_id.id,
                              'production_id': production_id.id}
            warning_log_line = {'state': None, 'product_id': product_id.id,
                                'workorder_id': workorder_id.id,
                                'workcenter_id': workcenter_id.id}
            if not workcenter_id.contract_id:
                activity_window = self.baseline_id.lookahead_window or 1
                current_period = workcenter_id.period_group_id.period_ids. \
                    filtered(lambda _r: _r.from_date < datetime.now() <= _r.to_date)
                activity_period = workcenter_id.period_group_id.period_ids. \
                    filtered(lambda _r: _r.from_date < date_start <= _r.to_date)
                if activity_period and current_period and \
                        activity_period.global_sequence <= current_period.global_sequence + activity_window:
                    warning_log_line.update({'state': 'contract'})

            if production_id.type != 'operational':
                analytic_ids = analytic_ids
            elif contract_id and contract_id.analytic_account_id:
                analytic_ids = [contract_id.analytic_account_id.id]
            else:
                analytic_ids = []

            if not analytic_ids and production_id.type == 'operational':
                error_log_line.update({'state': 'analytic'})
            elif not analytic_ids and production_id.type != 'operational':
                error_log_line.update({'state': 'analytic_production'})

            if period_group_id:
                tmp_start = self.env['time.tracking.actions'].get_tz_datetime(date_start, self.env.user)
                tmp_end = self.env['time.tracking.actions'].get_tz_datetime(date_end, self.env.user)
                total_duration = self.get_duration_by_calendar(calendar_id, tmp_start, tmp_end)
                if total_duration == 0:
                    warning_log_line.update({'state': 'duration'})
            else:
                error_log_line.update({'state': 'period_group'})

            if error_log_line['state']:
                error_log.append(error_log_line)
            if warning_log_line['state']:
                warning_log.append(warning_log_line)
        return error_log, warning_log

    def get_schedule_by_day(self, calendar_id, date):
        blocks = []
        for att in calendar_id.attendance_ids.filtered(lambda r: r.dayofweek == str(date.weekday())):
            from_hour = int('{0:02.0f}'.format(*divmod(att.hour_from * 60, 60)))
            from_minutes = int('{1:02.0f}'.format(*divmod(att.hour_from * 60, 60)))
            to_hour = int('{0:02.0f}'.format(*divmod(att.hour_to * 60, 60)))
            to_minutes = int('{1:02.0f}'.format(*divmod(att.hour_to * 60, 60)))

            day_start = date.replace(hour=from_hour, minute=from_minutes, second=0)
            day_end = date.replace(hour=to_hour, minute=to_minutes, second=0)
            blocks.append(day_start)
            blocks.append(day_end)
        blocks.sort()
        if blocks:
            return self.env['time.tracking.actions'].remove_tz_datetime(blocks[0], self.env.user),\
                   self.env['time.tracking.actions'].remove_tz_datetime(blocks[-1], self.env.user)
        else:
            return None, None

    def get_duration_by_calendar(self, calendar_id, date_start, date_end):
        total_minutes = 0
        while date_start.strftime('%Y-%m-%d') <= date_end.strftime('%Y-%m-%d'):
            for att in calendar_id.attendance_ids.filtered(lambda r: r.dayofweek == str(date_start.weekday())):
                from_hour = int('{0:02.0f}'.format(*divmod(att.hour_from * 60, 60)))
                from_minutes = int('{1:02.0f}'.format(*divmod(att.hour_from * 60, 60)))
                to_hour = int('{0:02.0f}'.format(*divmod(att.hour_to * 60, 60)))
                to_minutes = int('{1:02.0f}'.format(*divmod(att.hour_to * 60, 60)))

                block_start = date_start.replace(hour=from_hour, minute=from_minutes, second=0)
                block_end = date_start.replace(hour=to_hour, minute=to_minutes, second=0)
                if block_end > date_start:
                    if block_start < date_start:
                        block_start = date_start
                    if block_end > date_end:
                        block_end = date_end
                    if block_end > block_start:
                        total_minutes += (block_end - block_start).total_seconds() / 60
            date_start = (date_start + timedelta(days=1)).replace(hour=0, minute=0, second=1)
        return total_minutes

    def show_flowline_btn(self):
        action = self.env.ref('aci_lbm_flowline.lbm_scenario_flowline_action').read()[0]
        action['context'] = {'search_default_render': 1}
        action['domain'] = [('scenario_id', '=', self.id)]
        return action


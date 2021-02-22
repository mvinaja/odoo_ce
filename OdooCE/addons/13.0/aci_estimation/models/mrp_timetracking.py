# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from odoo.http import request
import random
import datetime
from datetime import timedelta

class Followers(models.Model):
    _inherit = 'mail.followers'

    @api.model
    def create(self, vals):
        if 'res_model' in vals and 'res_id' in vals and 'partner_id' in vals:
            dups = self.env['mail.followers'].search([('res_model', '=',vals.get('res_model')),
                                               ('res_id', '=', vals.get('res_id')),
                                               ('partner_id', '=', vals.get('partner_id'))])
            if len(dups):
                for p in dups:
                    p.unlink()
        res = super(Followers, self).create(vals)
        return res


class MrpTimetrackingWorkorder(models.TransientModel):
    _name = 'mrp.timetracking.replanning'
    _description = 'mrp.timetracking.replanning'

class MrpTimetrackingWorkorder(models.Model):
    _name = 'mrp.timetracking.workorder'
    _description = 'mrp.timetracking.workorder'
    _rec_name = 'workorder_id'

    workorder_id = fields.Many2one('mrp.workorder', ondelete='cascade', readonly=True)
    party_id = fields.Many2one(related='workorder_id.product_wo.party_id', store=True)
    warehouse_id = fields.Many2one(related='workorder_id.warehouse_id', readonly=True)
    planned_workcenter_id = fields.Many2one('mrp.workcenter', string='BL Workcenter')
    workcenter_id = fields.Many2one('mrp.workcenter',  string='Est Workcenter', compute='_compute_workcenter_id', store=True, readonly=False)
    employee_id = fields.Many2one(related='workcenter_id.employee_id')
    workcenter_code = fields.Char('Est Wkc', compute='_compute_workcenter_code', readonly=True)
    planned_workcenter_code = fields.Char('BL Wkc', compute='_compute_workcenter_code', readonly=True)

    production_id = fields.Many2one(related='workorder_id.production_id', readonly=True)
    product_id = fields.Many2one(related='workorder_id.product_wo', readonly=True)
    product_tmpl_id = fields.Many2one(related='product_id.product_tmpl_id', store=True, readonly=True)
    version = fields.Integer(related='workorder_id.operation_id.version')
    product_model = fields.Char(related='workorder_id.product_id.name', string='Mod.')
    lbm_workorder_id = fields.Many2one('lbm.workorder', ondelete='set null')
    baseline_id = fields.Many2one(related='lbm_workorder_id.scenario_id.baseline_id')
    operators_qty = fields.Integer(related='lbm_workorder_id.operators_qty', string='Oper.')
    start_date = fields.Datetime()
    end_date = fields.Datetime()

    planned_progress = fields.Float(string='% BL')
    ite_progress = fields.Float(string='% ITE')
    accum_executed_progress = fields.Float(string='% Acc', compute='_compute_executed')
    executed_progress = fields.Float(string='% Exec', compute='_compute_executed')
    replanning_progress = fields.Float(string='% Rep', compute='_compute_replanning')
    approved_progress = fields.Float(string='% Apvd')

    planned_qty_progress = fields.Float(string='BL')
    ite_qty_progress = fields.Float(string='ITE')
    accum_executed_qty_progress = fields.Float(string='Acc', compute='_compute_executed')
    executed_qty_progress = fields.Float(string='Exec', compute='_compute_executed')
    replanning_qty_progress = fields.Float(string='Rep', compute='_compute_replanning')
    approved_qty_progress = fields.Integer(string='Apvd', compute='_compute_approved')

    duration = fields.Float()

    period_group_id = fields.Many2one(related='period_id.group_id')
    period_id = fields.Many2one('payment.period', string='BL period', ondelete='cascade')
    ite_period_id = fields.Many2one('payment.period', string='ITE period ID', ondelete='cascade')
    period = fields.Char(compute='_compute_period', string='ITE period', store=True, readonly=False)

    analytic_id = fields.Many2one(related='production_id.project_id', string='Analytic ID', store=True)
    analytic_name = fields.Char(related='analytic_id.name', string='Analytic')
    has_timetracking = fields.Boolean(compute='_compute_has_timetracking')
    is_closed = fields.Boolean(default=False)
    manage_type = fields.Selection(related='workorder_id.manage_type')
    timetracking_type = fields.Selection([('workorder', 'Workorder'), ('mixed', 'Mixed')], required=True)
    track_workstep = fields.Boolean(compute='_compute_track_workstep', store=True)
    main_period = fields.Boolean(compute='_compute_main_period')
    can_be_planned = fields.Boolean(related='workorder_id.can_be_planned', readonly=False)
    use_restriction = fields.Boolean(related='workorder_id.use_restriction', string='Rest.Dom.')
    active_restriction_count = fields.Integer(related='workorder_id.active_restriction_count', string='Act.Rest')
    can_be_estimated = fields.Boolean(default=False)
    on_estimation = fields.Integer(compute='_compute_on_estimation', store=True)
    buy_required = fields.Boolean(related='workorder_id.buy_required')

    def write(self, values):
        res = super(MrpTimetrackingWorkorder, self).write(values)
        if 'approved_progress' in values.keys():
            for _id in self:
                if values.get('approved_progress') > _id.executed_progress:
                    raise UserError(_('You can only approve up to {}%'.format(_id.executed_progress)))
        return res

    @api.depends('planned_workcenter_id')
    def _compute_workcenter_id(self):
        for r in self:
            r.workcenter_id = r.planned_workcenter_id.id if not r.workcenter_id else r.workcenter_id.id

    @api.depends('workcenter_id', 'planned_workcenter_id', 'employee_id')
    def _compute_workcenter_code(self):
        for r in self:
            r.workcenter_code = '{}{}'.format(r.workcenter_id.code, ' ({})'.format(r.employee_id.code)
            if r.employee_id.code else '')
            r.planned_workcenter_code = '{}{}'.format(r.planned_workcenter_id.code if r.planned_workcenter_id else 'NA',
                                                      ' ({})'.format(r.planned_workcenter_id.employee_id.code)
            if r.planned_workcenter_id.employee_id.code else '')

    @api.depends('planned_start_date', 'planned_end_date')
    def _compute_date(self):
        for r in self:
            r.start_date = r.planned_start_date
            r.end_date = r.planned_end_date

    @api.depends('period_id', 'workorder_id')
    def _compute_has_timetracking(self):
        for r in self:
            timetracking_ids = self.env['mrp.timetracking'].search([('workorder_id', '=', r.workorder_id.id),
                                                                    ('date_start', '>=',
                                                                     r.period_id.from_date),
                                                                    ('date_start', '<=',
                                                                     r.period_id.to_date)])
            r.has_timetracking = True if len(timetracking_ids) >= 1 else False

    @api.depends('workcenter_id', 'can_be_estimated', 'ite_progress')
    def _compute_on_estimation(self):
        for r in self:
            estimation_ids = self.env['mrp.estimation'].search([('workcenter_id', '=', r.workcenter_id.id),
                                               ('period_id', '=', r.ite_period_id.id)])
            r.on_estimation = 100 if len(estimation_ids) >= 1 else 0

    @api.depends('ite_period_id', 'workorder_id')
    def _compute_executed(self):
        for r in self:
            wo_tracking = r.workorder_id.tracking_ids.filtered(lambda y: y.tracking_origin == 'workorder' and
                                                                         r.ite_period_id.from_date < y.final_start_date
                                                                         <= r.ite_period_id.to_date)
            percent_wo_complete = round(sum(wo_tracking.mapped('progress')), 2)
            percent_step_complete = 0
            for step_id in r.workorder_id.step_ids:
                tracking_qty = round(sum(step_id.tracking_ids.filtered(lambda y:
                                                                       r.period_id.from_date < y.final_start_date <= r.period_id.to_date and y.tracking_origin == 'step').mapped(
                    'qty_progress')), 2)
                percent_complete = tracking_qty / step_id.product_qty * 100 if step_id.product_qty else 0
                wo_complete = percent_complete * step_id.tracking_ratio
                percent_step_complete += wo_complete if wo_complete <= 100 else step_id.tracking_ratio * 100

            r.executed_progress = percent_wo_complete + percent_step_complete
            r.executed_qty_progress = r.executed_progress * r.workorder_id.qty_production / 100

            # Accumulated

            wo_tracking = r.workorder_id.tracking_ids.filtered(lambda y: y.tracking_origin == 'workorder' and
                                                                         y.final_start_date <= r.ite_period_id.to_date)
            percent_wo_complete = round(sum(wo_tracking.mapped('progress')), 2)
            percent_step_complete = 0
            for step_id in r.workorder_id.step_ids:
                tracking_qty = round(sum(step_id.tracking_ids.filtered(lambda y: y.final_start_date <=
                                                                                 r.period_id.to_date and y.tracking_origin == 'step').mapped(
                    'qty_progress')), 2)
                percent_complete = tracking_qty / step_id.product_qty * 100 if step_id.product_qty else 0
                wo_complete = percent_complete * step_id.tracking_ratio
                percent_step_complete += wo_complete if wo_complete <= 100 else step_id.tracking_ratio * 100

            r.accum_executed_progress = percent_wo_complete + percent_step_complete
            r.accum_executed_qty_progress = r.accum_executed_progress * r.workorder_id.qty_production / 100

    @api.depends('ite_progress', 'ite_qty_progress', 'executed_progress', 'executed_qty_progress')
    def _compute_replanning(self):
        for r in self:
            r.replanning_progress = r.ite_progress - r.executed_progress
            r.replanning_qty_progress = r.ite_qty_progress - r.executed_qty_progress
            if r.replanning_progress < 0:
                r.replanning_progress = 0
                r.replanning_qty_progress = 0

    @api.depends('workorder_id', 'approved_progress')
    def _compute_approved(self):
        for r in self:
            r.approved_qty_progress = r.approved_progress * r.workorder_id.qty_production / 100

    @api.depends('period_id', 'ite_period_id')
    def _compute_period(self):
        for r in self:
            r.period = r.ite_period_id.name if not r.period else r.period

    @api.depends('workorder_id.step_ids')
    def _compute_track_workstep(self):
        for r in self:
            r.track_workstep = True if r.workorder_id.step_ids else False

    @api.depends('ite_period_id', 'period_id')
    def _compute_main_period(self):
        for r in self:
            r.main_period = True if r.ite_period_id.id == r.period_id.id else False

    def show_tracking_btn(self):
        timetracking_ids = self.env['mrp.timetracking'].search([('workorder_id', '=', self.workorder_id.id),
                                                                    ('date_start', '>=',
                                                                     self.period_id.from_date),
                                                                    ('date_start', '<=',
                                                                     self.period_id.to_date)])
        view_id = self.env['ir.model.data'].get_object(
            'aci_estimation', 'mrp_timetracking_tree_view')
        calendar_view_id = self.env['ir.model.data'].get_object(
            'aci_estimation', 'mrp_timetracking_calendar_view')
        return {
            'type': 'ir.actions.act_window',
            'name': 'Activity',
            'views': [(view_id.id, 'tree'), (calendar_view_id.id, 'calendar')],
            'res_model': 'mrp.timetracking',
            'domain': [('id', 'in', timetracking_ids.ids)],
            'target': 'current'
        }

    def random_tracking_btn(self, context=None):
        context = self.env.context
        lbm_workorder_ids = self.browse(context.get('active_ids')).filtered(lambda r: r.track_workstep is True)
        for period_id in lbm_workorder_ids.mapped('period_id'):
            product_ids = lbm_workorder_ids.filtered(lambda r: r.period_id.id == period_id.id).mapped('product_id')
            for product_id in product_ids:
                workorder_ids = lbm_workorder_ids.filtered(lambda r: r.period_id.id == period_id.id and \
                                                          r.product_id.id == product_id.id)
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

    def is_closed_btn(self):
        self.is_closed = True

    def is_open_btn(self):
        self.is_closed = False

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
        # if not self.env.user.has_group('aci_estimation.group_estimation_chief'):
        #     raise UserError(_('You are not allowed to do this process'))
        context = self.env.context
        workorder_ids = self.browse(context.get('active_ids'))
        for workorder_id in workorder_ids:
            # workorder_id.use_restriction = use_restriction
            workorder_id.can_be_estimated = not use_restriction

    def block_workorder_btn(self, context=None):
        self.change_can_be_planned(True)

    def open_workorder_btn(self, context=None):
        self.change_can_be_planned(False)

    def move_replanning_workorder_btn(self):
        view_id = self.env['ir.model.data'].get_object(
            'aci_estimation', 'lbm_period_move_view_tree')
        _ids = []
        lbm_period_id = self.env['lbm.period'].search([('baseline_id', '=', self.baseline_id.id),
                                                       ('period_start', '<=', self.start_date),
                                                       ('period_end', '>=', self.start_date)])
        lbm_period_ids = self.env['lbm.period'].search([('baseline_id', '=', self.baseline_id.id),
                                                        ('period_group', '=', self.period_group_id.id),
                                                        ('id', '!=', lbm_period_id.id)])
        for lbm_period_id in lbm_period_ids:
            workorder_ids = self.env['mrp.timetracking.workorder'].search([('baseline_id', '=', self.baseline_id.id),
                                                                           ('start_date', '>=',
                                                                            lbm_period_id.period_start),
                                                                           ('start_date', '<=',
                                                                            lbm_period_id.period_end)])
            if self.workorder_id.id not in workorder_ids.ids:
                _ids.append(lbm_period_id.id)

        return {
            'type': 'ir.actions.act_window',
            'name': 'Move Wo',
            'views': [(view_id.id, 'tree')],
            'res_model': 'lbm.period',
            'target': 'new',
            'domain': [('id', 'in', _ids)],
            'context': {'ite_ids': [self.id]}
        }

    def show_calculator(self, model_name, field_name, res_id, res_value, mode):
        return {
            'type': 'ir.actions.act_window',
            'views': [(False, 'form')],
            'view_mode': 'form',
            'name': 'Calculator//small',
            'res_model': 'mrp.estimation.calculator',
            'target': 'new',
            'aci_size': 'small',
            'context': {'default_model_name': model_name,
                        'default_field_name': field_name,
                        'default_res_id': res_id,
                        'default_mode': mode,
                        'default_float_result': res_value,
                        'default_int_result': res_value}
        }

    def show_approved_progress_calculator_btn(self, context=None):
        return self.show_calculator('mrp.timetracking.workorder', 'approved_progress', self.id, self.approved_progress, 'integer')

    def show_estimation_btn(self):
        Estimation = self.env['mrp.estimation']
        view_id = self.env['ir.model.data'].get_object(
            'aci_estimation', 'mrp_estimation_form_view')
        estimation_id = Estimation.search([('workcenter_id', '=', self.workcenter_id.id),
                                           ('start_period', '<=', self.start_date),
                                           ('end_period', '>=', self.end_date),
                                           ('estimation_type', '=', 'period'),
                                           ('warehouse_id', '=', self.warehouse_id.id)])
        return {
            'name': 'Estimation',
            'res_model': 'mrp.estimation',
            'type': 'ir.actions.act_window',
            'view_id': view_id.id,
            'target': 'current',
            'res_id': estimation_id.id,
            'view_type': 'form',
            'view_mode': 'form',
        }

    def create_distribution_btn(self, context=None):
        if not self.env.user.has_group('aci_estimation.group_estimation_resident'):
            raise ValidationError(_('You are not allowed to do this process'))

        if self._context.get('active_model', None) == 'lbm.period':
            lbm_period_id = self.env['lbm.period'].browse([self._context.get('active_id')])
            lbm_period_id.distribution_validated = False
            lbm_period_id.tracking_validated = False
            lbm_period_id.create_distribution()
            lbm_period_id.distribution_validated = True

    def process_replanning_btn(self, context=None):
        for tworkorder_id in self.browse(self._context.get('active_ids', None)).filtered(lambda r: r.can_be_estimated is True):
            lbm_period_id = self.env['lbm.period'].search([('baseline_id', '=', tworkorder_id.baseline_id.id),
                                                           ('period_start', '<=', tworkorder_id.start_date),
                                                           ('period_end', '>=', tworkorder_id.start_date)])
            lbm_period_id.process_replanning_btn(workorder_id=tworkorder_id.workorder_id.id)

    def buy_required_btn(self, context=None):
        for workorder_id in self.browse(self._context.get('active_ids', None)).mapped('workorder_id'):
            workorder_id.buy_required = not workorder_id.buy_required


class MrpTimetracking(models.Model):
    _inherit = ['mail.activity.mixin', 'mail.thread']
    _name = 'mrp.timetracking'
    _description = 'MRP TimeTracking'
    _order = 'date_start,sequence'
    _rec_name = 'product_id'

    _sql_constraints = [
        ('unique_key', 'unique(baseline_id, production_id, workorder_id, step_id, period_id, analytic_id, month_number, day_number)', 'Key already exists.')]

    def _get_default_stage_id(self):
        Stage = self.env['mrp.timetracking.stage']
        stage_id = Stage.search([('name', '=', 'ToDo')], limit=1)
        return stage_id.id

    available = fields.Boolean(default=True)  # Available is used if it a key that should be removed but it has input
    timetracking_type = fields.Selection([('workorder', 'Workorder'), ('mixed', 'Mixed')])  # Active is used if its timetracking type and period
    timetracking_active = fields.Boolean(compute='_compute_timetracking_active', store=True)  # are consisted with the Wo. Configuration
    baseline_id = fields.Many2one('lbm.baseline', 'Baseline', readonly=True, ondelete='set null')
    production_id = fields.Many2one(related='workorder_id.production_id', store=True, ondelete='cascade')
    production_type = fields.Selection(related='production_id.type', readonly=True)
    warehouse_id = fields.Many2one(related='workorder_id.warehouse_id', ondelete='cascade', store=True)
    workorder_id = fields.Many2one('mrp.workorder', ondelete='cascade', readonly=True)
    version = fields.Integer(related='workorder_id.operation_id.version')
    product_model = fields.Char(related='workorder_id.product_id.name', string='Mod.')
    step_id = fields.Many2one('lbm.work.order.step', ondelete='cascade', readonly=True)
    analytic_id = fields.Many2one('account.analytic.account', string='Analytic Account', ondelete='restrict', readonly=True)
    analytic_id_name = fields.Char(compute='_compute_analytic_id_name')
    period_group_id = fields.Many2one('payment.period.group', string='Planned Period Group', readonly=True)
    lbm_period_id = fields.Many2one('payment.period', readonly=True, ondelete='restrict')
    planned_period_id = fields.Many2one('payment.period', readonly=True, ondelete='restrict')
    manual_period_id = fields.Many2one('payment.period', ondelete='restrict')
    period_id = fields.Many2one('payment.period', compute='_compute_period', string='Exec. Period',
                                store=True, readonly=True, ondelete='restrict')
    period_from = fields.Datetime(related='period_id.from_date')
    period_to = fields.Datetime(related='period_id.to_date')

    key = fields.Char()

    tracking_origin = fields.Selection([
        ('step', 'Step'),
        ('workorder', 'WorkOrder'),
        ('activity', 'Activity')], default='step', required=True)

    planned_workcenter_id = fields.Many2one('mrp.workcenter')
    manual_workcenter_id = fields.Many2one('mrp.workcenter')
    workcenter_id = fields.Many2one('mrp.workcenter', compute='_compute_workcenter', string='Exec. Workcenter', store=True)
    workcenter_code = fields.Char('Workcenter Code', compute='_compute_workcenter_code', readonly=True)
    calendar_id = fields.Many2one('resource.calendar', 'Working Schedule')
    estimation_workcenter_id = fields.Many2one('mrp.estimation.workcenter', compute='_compute_estimation_workcenter')
    block_origin = fields.Selection(related='estimation_workcenter_id.block_origin')
    employee_id = fields.Many2one(related='workcenter_id.employee_id', readonly=True)
    department_id = fields.Many2one(related='employee_id.department_id', readonly=True)
    product_id = fields.Many2one('product.product', compute='_compute_product', store=True)
    product_tmpl_id = fields.Many2one('product.template', compute='_compute_product', store=True)
    short_name = fields.Char('Step Short Name', compute='_compute_short_name')
    attribute_name = fields.Char('Step Attribute Name', compute='_compute_short_name')
    bomline_wbs = fields.Char(compute='_compute_bomline')
    bomline_sequence = fields.Char(compute='_compute_bomline')
    category_filter = fields.Char(compute='_compute_category_filter', store=True)
    party_id = fields.Many2one(related='workorder_id.product_wo.party_id')

    stage_id = fields.Many2one('mrp.timetracking.stage', string='Stage', default=_get_default_stage_id)
    production_type = fields.Selection(related='production_id.type', store=True)
    date_start = fields.Datetime(readonly=True)
    date_end = fields.Datetime(readonly=True)
    date_end_day = fields.Char(compute='_compute_date_end_day')
    step_type = fields.Selection(related='product_id.step_type', readonly=True)
    add_value = fields.Boolean(related='product_id.add_value', readonly=True)
    restricted_qty = fields.Boolean(related='production_id.bom_id.type_qty', readonly=True)

    tracking_ids = fields.One2many('mrp.workcenter.productivity', 'timetracking_id')
    quality_alert_ids = fields.One2many('quality.alert', 'timetracking_id')
    real_duration_expected = fields.Float(compute='_compute_duration_expected', store=True)
    duration_expected = fields.Float(compute='_compute_duration_expected', store=True)
    accum_time = fields.Float('Duration', compute='_compute_duration', default=0)
    product_uom_id = fields.Many2one('uom.uom', string='Product UoM',
        related='product_id.uom_id')
    product_qty = fields.Float(string='Quantity', compute="_compute_product_qty")
    progress = fields.Float(string='% Progress', compute="_compute_progress_qty")
    progress_qty = fields.Float(string='Progress Qty', compute="_compute_progress_qty")
    expected_qty = fields.Float(string='Expected')
    expected_percentage = fields.Integer(compute='_compute_expected_percentage')
    expected_wo_percentage = fields.Integer(compute='_compute_expected_percentage')
    sequence = fields.Integer(default=0)  # DEPRECATED
    month_number = fields.Integer(default=0)
    day_number = fields.Integer(default=0)
    active_on_period = fields.Boolean(compute='_compute_active_on')
    estimation_type = fields.Selection(related='workcenter_id.estimation_type', store=True)
    percent_complete = fields.Integer(compute='_compute_percent_complete')
    percent_wo_complete = fields.Integer(string='WO Progress', compute="_compute_percent_complete")
    has_restriction = fields.Boolean(related='workorder_id.active_restriction', store=True)
    unlock_restriction = fields.Boolean(compute='_compute_unlock_restriction', store=True)
    activity_id = fields.Many2one('mail.activity', ondelete='cascade')
    activity_workcenter_id = fields.Many2one('mrp.workcenter')
    activity_product_id = fields.Many2one('product.product')
    set_operators = fields.Boolean(related='workcenter_id.set_operators')

    @api.model
    def create(self, vals):
        res = super(MrpTimetracking, self).create(vals)
        estimation_ids = self.env['mrp.estimation'].search([('workcenter_id', 'in', res.mapped('workcenter_id').ids),
                                                            ('estimation_type', '=', 'period'),
                                                            ('start_period', '<=', res.date_start),
                                                            ('end_period', '>=', res.date_start),
                                                            ('warehouse_id', '>=', res.warehouse_id.id)])
        if estimation_ids:
            for estimation_id in estimation_ids:
                if not estimation_id.period_status or estimation_id.period_status in ('draft', 'open'):
                    estimation_id.update_planned_btn()
                else:
                    raise ValidationError("The estimation is not open anymore.")
        return res

    @api.depends('workcenter_id', 'employee_id')
    def _compute_workcenter_code(self):
        for r in self:
            r.workcenter_code = '{}{}'.format(r.workcenter_id.code, ' ({})'.format(r.employee_id.code)
                if r.employee_id.code else '')

    @api.depends('timetracking_type', 'tracking_origin')
    def _compute_timetracking_active(self):
        for r in self:
            r.timetracking_active = True if r.timetracking_type == r.tracking_origin or r.timetracking_type == 'mixed' else False

    @api.depends('analytic_id')
    def _compute_analytic_id_name(self):
        for r in self:
            r.analytic_id_name = r.analytic_id.name

    @api.depends('workcenter_id')
    def _compute_active_on(self):
        for r in self:
            current_period = r.workcenter_id.period_group_id.period_ids. \
                filtered(lambda _r: _r.from_date < datetime.datetime.now() <= _r.to_date)
            r.active_on_period = True if r.period_id.id == current_period.id else False

    @api.depends('step_id', 'workorder_id', 'manual_workcenter_id', 'planned_workcenter_id')
    def _compute_workcenter(self):
        for r in self:
            r.workcenter_id = r.manual_workcenter_id.id if r.manual_workcenter_id else r.planned_workcenter_id.id

    @api.depends('workcenter_id')
    def _compute_estimation_workcenter(self):
        Wkcenter = self.env['mrp.estimation.workcenter']
        for r in self:
            r.estimation_workcenter_id = Wkcenter.search([('workcenter_id', '=', r.workcenter_id.id)]).id

    @api.depends('period_group_id', 'manual_period_id', 'planned_period_id')
    def _compute_period(self):
        for r in self:
            r.period_id = r.manual_period_id.id if r.manual_period_id else r.planned_period_id

    @api.depends('step_id', 'workorder_id', 'activity_product_id')
    def _compute_product(self):
        for r in self:
            if not r.activity_product_id:
                r.product_id = r.step_id.product_id.id if r.step_id else r.workorder_id.product_wo.id
            else:
                r.product_id = r.activity_product_id.id
            r.product_tmpl_id = r.product_id.product_tmpl_id.id

    @api.depends('product_id')
    def _compute_short_name(self):
        for step in self:
            short_name = step.product_id.name if len(step.product_id.name) <= 25 else str(step.product_id.name)[:25]
            attribute_name = '({})'
            pre_name = ''
            for att in step.product_id.attribute_value_ids:
                pre_name += '{} '.format(att.name)
            pre_name = pre_name if len(pre_name) <= 25 else pre_name[:25]
            step.short_name = short_name
            step.attribute_name = attribute_name.format(pre_name)

    @api.depends('workorder_id', 'product_id')
    def _compute_bomline(self):
        for r in self:
            r.bomline_wbs = self.env['mrp.bom'].search([('product_id', '=', r.product_id.id)], limit=1).wbs_key
            r.bomline_sequence = self.env['mrp.bom'].search([('product_id', '=', r.product_id.id)], limit=1).sequence

    @api.depends('step_id.workstep_id.categ_id', 'workorder_id.product_id', 'analytic_id')
    def _compute_category_filter(self):
        for r in self:
            r.category_filter = r.step_id.workstep_id.categ_id.name if r.step_id \
                else '{} {}'.format(r.analytic_id.name, r.workorder_id.product_id.name)

    @api.depends('date_end')
    def _compute_date_end_day(self):
        for r in self:
            r.date_end_day = '{}({})'.format(r.period_id.name, r.date_end.strftime('%a'))

    @api.depends('date_start', 'date_end', 'workcenter_id', 'calendar_id')
    def _compute_duration_expected(self):
        for r in self:
            start = self.env['time.tracking.actions'].get_tz_datetime(r.date_start, self.env.user)
            end = self.env['time.tracking.actions'].get_tz_datetime(r.date_end, self.env.user)
            r.real_duration_expected = self.env['lbm.scenario'].get_duration_by_calendar(r.calendar_id, start, end)
            r.duration_expected = r.real_duration_expected / len(r.workorder_id.step_ids) if r.step_id else r.real_duration_expected


    @api.depends('tracking_ids.duration')
    def _compute_duration(self):
        for r in self:
            r.accum_time = sum(r.tracking_ids.mapped('duration')) / 60

    @api.depends('product_id')
    def _compute_product_qty(self):
        for r in self:
            r.product_qty = r.step_id.product_qty if r.step_id else r.workorder_id.qty_production

    @api.depends('tracking_ids.qty_progress')
    def _compute_progress_qty(self):
        for r in self:
            r.progress_qty = sum(r.tracking_ids.mapped('qty_progress'))
            r.progress = sum(r.tracking_ids.mapped('progress'))

    @api.depends('expected_qty', 'product_qty', 'step_id')
    def _compute_expected_percentage(self):
        for r in self:
            r.expected_percentage = int(round(r.expected_qty * 100 / r.product_qty, 2))
            r.expected_wo_percentage = int(round(r.expected_percentage * r.step_id.tracking_ratio / 100 * 100, 2)) if r.step_id else r.expected_percentage

    @api.depends('workorder_id', 'step_id')
    def _compute_percent_complete(self):
        for r in self:
            if r.step_id:
                r.percent_complete = int(r.step_id.percent_complete)
            else:
                r.percent_complete = int(r.workorder_id.percent_wo_complete)
            r.percent_wo_complete = int(r.workorder_id.percent_complete)

    def button_timeoff(self):
        block_ids = self.env['hr.productivity.block'].search([('employee_id', '=', self.workcenter_id.employee_id.id),
                                                              ('block_origin', '=', 'timeoff')])
        block_id = None
        for _ids in block_ids:
            _date = self.env['time.tracking.actions'].get_tz_datetime(_ids.final_start_date, self.env.user)
            if _date.strftime("%Y-%m-%d") == datetime.datetime.now().strftime("%Y-%m-%d"):
                block_id = _ids.id
                break

        action = {
            'type': 'ir.actions.act_window',
            'views': [(False, 'form')],
            'view_mode': 'form',
            'name': 'Time Off',
            'res_model': 'hr.productivity.block.timeoff',
            'target': 'new',
            'context': {'default_employee_id': self.workcenter_id.employee_id.id,
                        'default_date': datetime.datetime.now(),
                        'default_block_id': block_id}
        }
        return action

    def button_blocks(self):
        return self.estimation_workcenter_id.button_blocks()

    def button_activity(self):
        origin = self._context.get('origin')
        search_args = [('resource_id', '=', self.workcenter_id.id),
                       ('date_start', '>=', datetime.datetime.today().replace(hour=00, minute=00, second=1)),
                       ('date_start', '<=', datetime.datetime.today().replace(hour=23, minute=59, second=59))]
        if origin:
            if origin[0] == 'step':
                search_args.append(('step_id', '!=', False))
            else:
                search_args.append(('step_id', '=', False))
        return {
            'name': 'Daily Activity',
            'res_model': 'mrp.workcenter.productivity',
            'type': 'ir.actions.act_window',
            'view_mode': 'timeline,tree,form,pivot,kanban,graph',
            'target': 'current',
            'domain': search_args
        }

    def button_quality_alert_planned(self):
        form_view_id = self.env['ir.model.data'].get_object('aci_estimation', 'mrp_timetracking_form_view_quality')
        return {
            'name': _('Quality Alert'),
            'res_model': 'mrp.timetracking',
            'type': 'ir.actions.act_window',
            'views': [(form_view_id.id, 'form')],
            'target': 'new',
            'res_id': self.id
        }

    def button_activity(self):
        form_view_id = self.env['ir.model.data'].get_object('mail', 'mail_activity_view_form_popup')
        model_id = self.env['ir.model'].sudo().search([('model', '=', 'mrp.timetracking')])
        return {
            'name': _('Activity'),
            'res_model': 'mail.activity',
            'type': 'ir.actions.act_window',
            'views': [(form_view_id.id, 'form')],
            'target': 'new',
            "context": {'default_res_id': self.id, 'default_res_model_id': model_id.id}
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

    def button_edit_estimation(self):
        Block = self.env['hr.productivity.block']
        Productivity = self.env['mrp.workcenter.productivity']
        Estimation = self.env['mrp.estimation']
        Tworkorder = self.env['mrp.timetracking.workorder']

        view_id = self.env['ir.model.data'].get_object(
            'aci_estimation', 'mrp_timetracking_mixed_wizard_form_view')

        period_ids = Tworkorder.search([('workorder_id', '=', self.workorder_id.id),
                                        ('ite_progress', '>', 0),
                                        ('is_closed', '=', False)]).mapped('ite_period_id')

        estimation_id = Estimation.search([('workcenter_id', '=', self.workcenter_id.id),
                                           ('estimation_type', '=', 'period'),
                                           ('period_id', 'in', period_ids.ids),
                                           ('period_status', '=', 'open'),
                                           ('warehouse_id', '=', self.warehouse_id.id)], order='start_period ASC', limit=1)
        block_id = None
        start_date = None
        if not period_ids:
            raise UserError('Could not find a valid period for this workorder')
        if not estimation_id:
            periods = ''
            for period_id in period_ids:
                period_start = self.env['time.tracking.actions'].get_tz_datetime(period_id.from_date,
                                                                                 self.env.user)
                period_end = self.env['time.tracking.actions'].get_tz_datetime(period_id.to_date,
                                                                               self.env.user)

                periods = periods + '{} ({} to {}), '.format(period_id.name, period_start.strftime("%m/%d/%Y"),
                                                             period_end.strftime("%m/%d/%Y"))
            raise UserError('You need an OPEN estimation on any of this periods {}'.format(periods))

        prev_estimation_ids = Estimation.search([('workcenter_id', '=', self.workcenter_id.id),
                                                  ('estimation_type', '=', 'period'),
                                                  ('warehouse_id', '=', self.warehouse_id.id),
                                                  ('period_id', '!=', estimation_id.id)],
                                                  order='start_period ASC')
        if prev_estimation_ids:
            if prev_estimation_ids.filtered(lambda r: r.period_id.global_sequence < estimation_id.period_id.global_sequence
                                            and r.period_status in ('draft', 'open')):
                raise UserError('Close previous estimations')

        if estimation_id:
            search_args = [('employee_id', '=', self.workcenter_id.employee_id.id),
                           ('block_type', '=', 'active'),
                           ('warehouse_id', '=', self.warehouse_id.id),
                           ('block_origin', 'in', ('calendar', 'extra'))]

            period_start = estimation_id.period_id.from_date
            period_end = estimation_id.period_id.to_date
            productivity_id = Productivity.search([('employee_id', '=', self.workcenter_id.employee_id.id),
                                                   ('warehouse_id', '=', self.warehouse_id.id),
                                                   ('final_start_date', '>=', period_start),
                                                   ('final_end_date', '<=', period_end)],
                                                    order='final_end_date DESC', limit=1)

            if productivity_id:

                search_args.append(('final_start_date', '<=', productivity_id.final_end_date))
                search_args.append(('final_end_date', '>=', productivity_id.final_end_date))
            else:
                search_args.append(('final_start_date', '>=', period_start))
                search_args.append(('final_end_date', '<=', period_end))

            block_id = Block.search(search_args, order='final_start_date ASC', limit=1)

            if not productivity_id and block_id:
                start_date = block_id.final_start_date + timedelta(seconds=1)
            elif productivity_id and not block_id:
                search_args = [('employee_id', '=', self.workcenter_id.employee_id.id),
                               ('block_type', '=', 'active'),
                               ('block_origin', 'in', ('calendar', 'extra')),
                               ('warehouse_id', '=', self.warehouse_id.id),
                               ('final_start_date', '>=', productivity_id.final_end_date),
                               ('final_end_date', '<=', period_end)]
                block_id = Block.search(search_args, order='final_start_date ASC', limit=1)
                if block_id:
                    start_date = block_id.final_start_date + timedelta(seconds=1)
            elif productivity_id:
                start_date = productivity_id.final_end_date + timedelta(seconds=1)

            if productivity_id and block_id and productivity_id.final_end_date.replace(microsecond=0) == \
                    block_id.final_end_date.replace(microsecond=0):
                search_args = [('employee_id', '=', self.workcenter_id.employee_id.id),
                               ('block_type', '=', 'active'),
                               ('block_origin', 'in', ('calendar', 'extra')),
                               ('warehouse_id', '=', self.warehouse_id.id),
                               ('final_start_date', '>', block_id.final_end_date),
                               ('final_end_date', '<=', period_end)]
                block_id = Block.search(search_args, order='final_start_date ASC', limit=1)
                if block_id:
                    start_date = block_id.final_start_date + timedelta(seconds=1)
            if not self.env.context.get('can_input', True):
                raise UserError('This daily can not have inputs')

        qty_operators = self.env['lbm.workorder'].search([('workorder_id', '=', self.workorder_id.id)], limit=1).operators_qty
        Employee = self.env['mrp.timetracking.mixed.employee.wizard']
        employee_ids = []
        if start_date:
            start = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
            end = start_date.replace(hour=23, minute=59, second=59, microsecond=0)
            if Block.search([('employee_id', '=', self.employee_id.id),
                             ('final_start_date', '>=', start),
                             ('final_start_date', '<=', end),
                             ('warehouse_id', '=', self.warehouse_id.id),
                             ('block_available', '=', True)]):
                employee_ids.append(Employee.create({'employee_id': self.employee_id.id}).id)

            for employee_id in self.workcenter_id.employee_ids.ids:
                if Block.search([('employee_id', '=', employee_id),
                                 ('final_start_date', '>=', start),
                                 ('warehouse_id', '=', self.warehouse_id.id),
                                 ('final_start_date', '<=', end)]):
                    employee_ids.append(Employee.create({'employee_id': employee_id}).id)

        if not block_id:
            period_start = self.env['time.tracking.actions'].get_tz_datetime(estimation_id.period_id.from_date, self.env.user)
            period_end = self.env['time.tracking.actions'].get_tz_datetime(estimation_id.period_id.to_date, self.env.user)
            raise UserError('Could not find a valid activity block for period {} ({} to {})'.format(
                estimation_id.period_id.name, period_start.strftime("%m/%d/%Y"), period_end.strftime("%m/%d/%Y")))

        return {
            'name': 'Register Activity//small',
            'res_model': 'mrp.timetracking.mixed.wizard',
            'type': 'ir.actions.act_window',
            'view_id': view_id.id,
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_timetracking_id': self.id,
                        'default_block_id': block_id.id if block_id else None,
                        'default_start_date': start_date,
                        'default_qty_operators': qty_operators,
                        'default_employee_ids': [(6, False, employee_ids)]}
        }

    def button_start_activity_estimation(self):
        if not self.estimation_workcenter_id.on_calendar and\
                self.estimation_workcenter_id.contract_id.tolerance == 'restrictive':
            raise ValidationError(_('Warning! You are outside your calendar schedule'))
        elif not self.estimation_workcenter_id.on_calendar:
            self.estimation_workcenter_id.button_start_extra_activity()
        else:
            self.env['hr.productivity.block'].start_activity([self.workcenter_id.id])

    def button_end_activity_estimation(self):
        if not self.estimation_workcenter_id.on_calendar:
            self.estimation_workcenter_id.button_end_extra_activity()
        else:
            self.env['hr.productivity.block'].end_activity([self.workcenter_id.id])

    @api.depends('workcenter_id', 'product_id', 'workorder_id.activity_ids', 'activity_id')
    def _compute_unlock_restriction(self):
        for r in self:
            restriction_ids = self.env['mail.activity'].search([('activity_source', '!=', 'normal'),
                                                                ('tracking_state', '=', 'locked'),
                                                                ('product_id', '=', r.product_id.id)])
            unlock = [True for restriction_id in restriction_ids if r.workcenter_id.id in restriction_id.workcenter_ids.ids]
            r.unlock_restriction = True if len(unlock) > 0 else False

    def button_detailed_form(self):
        self.ensure_one()
        view_id = self.env['ir.model.data'].get_object(
            'aci_estimation', 'mrp_timetracking_form_view')
        return {
            'name': '{}'.format(self.product_id.name_get()[0][1]),
            'res_model': 'mrp.timetracking',
            'res_id': self.id,
            'type': 'ir.actions.act_window',
            'view_id': view_id.id,
            'view_mode': 'form',
            'target': 'current',
            'height': 'auto',
            'width': '100%',
        }

    def button_record_form(self):
        if self.step_id:
            return self.step_id.button_detailed_form()
        else:
            return self.workorder_id.button_detailed_form()

    def button_quality_alert(self):
        view_form_id = self.env['ir.model.data'].get_object(
            'aci_estimation', 'quality_alert_view_form_tracking')
        view_id = self.env['ir.model.data'].get_object(
            'quality_control', 'quality_alert_view_kanban')

        analytic_id = self._context.get('selected_analytic_id')
        default_analytic_id = analytic_id if analytic_id else None
        return {
            'name': 'Assign Quality Work Center',
            'res_model': 'quality.alert',
            'type': 'ir.actions.act_window',
            'views': [(view_id.id, 'kanban'), (view_form_id.id, 'form')],
            'target': 'current',
            'context': {'default_workcenter_id': self.workcenter_id.id,
                        'default_product_tmpl_id': self.product_id.product_tmpl_id.id,
                        'default_activity_product_id': self.product_id.id,
                        'default_type': 'production',
                        'default_analytic_id': default_analytic_id},
            'domain': [('id', 'in', self.env['quality.alert'].search([('product_id', '=', self.product_id.id),
                                                                      ('workcenter_id', '=', self.workcenter_id.id)]).ids)]
        }

    @api.model
    def action_tracking_step_redirect(self):
        if self.env.user.shared_account:
            if request.session.get('session_workcenter'):
                action = self.build_redirect_action(workcenter_id=self.env['mrp.workcenter'].browse(
                    [request.session.get('session_workcenter')]))
            else:
                action = self.env.ref('aci_estimation.mrp_tracking_action').read()[0]
        else:
            action = self.build_redirect_action()
        return action

    @api.model
    def action_tracking_wo_redirect(self):
        if self.env.user.shared_account:
            if request.session.get('session_workcenter'):
                action = self.build_redirect_action(type='workorder', workcenter_id=self.env['mrp.workcenter'].browse(
                    [request.session.get('session_workcenter')]))
            else:
                action = self.env.ref('aci_estimation.mrp_tracking_wo_action').read()[0]
        else:
            action = self.build_redirect_action(type='workorder')
        return action

    @api.model
    def action_tracking_step_active_redirect(self):
        if self.env.user.shared_account:
            if request.session.get('session_workcenter'):
                action = self.build_redirect_action(workcenter_id=self.env['mrp.workcenter'].browse(
                    [request.session.get('session_workcenter')]), active=True)
            else:
                action = self.env.ref('aci_estimation.mrp_tracking_active_action').read()[0]
        else:
            action = self.build_redirect_action(active=True)
        return action

    @api.model
    def action_tracking_wo_active_redirect(self):
        if self.env.user.shared_account:
            if request.session.get('session_workcenter'):
                action = self.build_redirect_action(type='workorder', workcenter_id=self.env['mrp.workcenter'].browse(
                    [request.session.get('session_workcenter')]), active=True)
            else:
                action = self.env.ref('aci_estimation.mrp_tracking_wo_active_action').read()[0]
        else:
            action = self.build_redirect_action(type='workorder', active=True)
        return action

    def build_redirect_action(self, type='step', workcenter_id=None, method='building', active=False, baseline_id=None,
                              period_id=None, filter_workcenter_id=None):
        if not workcenter_id:
            workcenter_id = self.env['mrp.workcenter'].search([('employee_id.user_id', '=', self.env.user.id)], limit=1)

        workcenter_ids, dic_supervised_wc = self.env['mrp.tracking.access'].get_supervised(workcenter_id.id)
        result = self.get_tracking_filter(workcenter_ids, [type, method, active, None, baseline_id, period_id, filter_workcenter_id],
                                          [], [True] * 7, [True] * 7)

        if result:
            view_id = result[0][0]
            gantt_view_id = result[0][1]
            display_name = 'tracking by {}'.format(type)
            _ids = result[4]

            ctx = {
                'filter_workcenter_ids': result[1],
                'origin': result[2],
                'filters': result[3],
                'period_group_ids': result[5],
                'period_ids': result[6],
                'department_ids': result[7],
                'workcenter_ids': result[8],
                'analytic_ids': result[9],
                'party_ids': result[10],
                'workorder_ids': result[11],
                'period_day_ids': result[12],
                'filters_active': result[13],
                'filters_display': result[14],
                'is_supervisor': True if len(workcenter_ids) > 1 else False
            }
            action = {
                'type': 'ir.actions.act_window',
                'domain': [('id', 'in', _ids)],
                'views': [(view_id, 'kanban'), (gantt_view_id, 'gantt')],
                'view_mode': 'kanban',
                'name': display_name,
                'res_model': 'mrp.timetracking',
                'context': ctx}
            context = dict(self.env.context or {})
            context.update(action)
            request.session['session_workcenter'] = workcenter_id.id
            return action
        return None

    @api.model
    def action_dashboard_estimation_redirect(self):
        if self.env.user.shared_account:
            if request.session.get('session_workcenter'):
                action = self.build_redirect_config_action(self.env['mrp.workcenter'].browse(
                    [request.session.get('session_workcenter')]))
            else:
                action = self.env.ref('aci_estimation.mrp_tracking_action').read()[0]
        else:
            action = self.build_redirect_config_action(workcenter_id=None)
        return action

    def build_redirect_config_action(self, workcenter_id=None):
        if not workcenter_id:
            workcenter_id = self.env['mrp.workcenter'].search([('employee_id.user_id', '=', self.env.user.id)], limit=1)
        supervised_wc, dic_supervised_wc = self.env['mrp.tracking.access'].get_supervised(workcenter_id.id)
        view_id = self.env['ir.model.data'].get_object(
            'aci_estimation', 'lbm_baseline_estimation_kanban_view')
        _ids = self.create_estimation_workcenter(supervised_wc)
        if self.env.user.has_group('aci_estimation.group_estimation_chief'):
            estimation_workcenter_ids = self.env['mrp.estimation.workcenter'].search([])
            _ids = estimation_workcenter_ids.ids
            supervised_wc = estimation_workcenter_ids.mapped('workcenter_id').ids
        # res_ids = self.env['mrp.estimation.workcenter'].browse(_ids)
        # baseline_ids = self.env['mrp.timetracking'].search([('workcenter_id', 'in', res_ids.mapped('workcenter_id').ids)]).mapped('baseline_id')
        baseline_ids = self.env['lbm.scenario'].search([]).filtered(lambda r: r.planning_type == 'replanning').mapped('baseline_id')

        action = {
            'type': 'ir.actions.act_window',
            'views': [(view_id.id, 'kanban')],
            'view_mode': 'kanban',
            'target': 'current',
            'name': _('Baseline'),
            'res_model': 'lbm.baseline',
            'domain': [('id', 'in', baseline_ids.ids)],
            'context': {'workcenter_ids': supervised_wc,
                        'parent_workcenter_id': workcenter_id.id,
                        'est_workcenter_ids': _ids}
        }
        context = dict(self.env.context or {})
        context.update(action)
        request.session['session_workcenter'] = workcenter_id.id
        return action

    def delete_estimation_workcenter(self):
        production_ids = self.env['lbm.scenario'].search([('planning_type', '=', 'replanning')]).baseline_id.\
            mapped('production_ids')
        workcenter_ids = production_ids.workorder_ids.mapped('resource_id').ids
        self.env['mrp.estimation.workcenter'].search([('workcenter_id', 'not in', workcenter_ids)]).unlink()

    def create_estimation_workcenter(self, workcenter_ids):
        res_ids = []
        Workcenter = self.env['mrp.estimation.workcenter']
        for wc in workcenter_ids:
            _id = Workcenter.search([('workcenter_id', '=', wc)])
            if not _id:
                _id = Workcenter.create({'workcenter_id': wc})
            res_ids.append(_id.id)
        return res_ids

    def show_baseline(self):
        workcenter_id = self._context.get('workcenter_id')
        if not workcenter_id:
            return False
        return [workcenter_id]

    def get_filter_data(self, workcenter_ids, origin):
        stage_id = self.env['time.tracking.actions'].get_stage_id('Finished')

        args = [('tracking_origin', '=', origin[0]),
                ('employee_id', '!=', None),
                ('available', '=', True),
                ('timetracking_active', '=', True)]

        if origin[4] is not None:
            args.append(('baseline_id', '=', origin[4]))

        if origin[5] is not None:
            args.append(('period_id', '=', origin[5]))

        if origin[6] is not None:
            args.append(('workcenter_id', '=', origin[6]))

        if origin[0] == 'activity':
            args.append(('product_id', '=', origin[3]))
            args.append(('workcenter_id', 'in', workcenter_ids))

        if origin[3] is not None and origin[0] != 'activity':
            args.append(('product_id', '=', origin[3]))
            args.append(('workcenter_id', 'in', workcenter_ids))

        if not self.env.user.has_group('aci_estimation.group_estimation_chief'):
            args.append(('workcenter_id', 'in', workcenter_ids))
        timetracking_ids = self.search(args)
        data = []
        for _id in timetracking_ids:
            valid = True
            if origin[2] is True and _id.active_on_period is False:
                valid = False
            if _id.stage_id.id == stage_id:
                valid = False
            if valid:
                time_position = _id.period_id._get_time_position()
                if time_position == 'Current Period':
                    time_position = ' (curr.)'
                period_name = _id.period_id.name + time_position
                analytic_name = '{}({})'.format(_id.analytic_id.name, _id.production_id.product_id.name if _id.production_id else _id.activity_id.activity_type_id.name)
                analytic_id = int('{}0{}'.format(_id.analytic_id.id, _id.production_id.id if _id.production_id else _id.activity_id.id))
                if origin[0] != 'activity':
                    period_day_id = int(_id.date_start.strftime('%y%m%d'))
                    period_day_name = _id.date_start.strftime('%a%d')
                    workcenter_code = _id.workcenter_code
                    record = [_id.id,
                             _id.workorder_id.id, _id.workorder_id.name,
                             analytic_id, analytic_name,
                             _id.workcenter_id.id, workcenter_code,
                             _id.department_id.id, _id.department_id.name,
                             period_day_id, period_day_name,
                             _id.period_id.id, period_name,
                             _id.period_group_id.id, _id.period_group_id.name]
                else:
                    period_day_id = 0 if _id.workcenter_id.estimation_type == 'period' else int(_id.date_end.strftime('%y%m%d'))
                    period_day_name = 'Period' if _id.workcenter_id.estimation_type == 'period' else _id.date_end.strftime('%a%d')
                    record = [_id.id,
                             _id.activity_id.id, _id.activity_id.summary,
                             analytic_id, analytic_name,
                             _id.workcenter_id.id, _id.workcenter_code,
                             _id.department_id.id, _id.department_id.name,
                             period_day_id, period_day_name,
                             _id.period_id.id, period_name,
                             _id.period_group_id.id, _id.period_group_id.name]
                data.append(record)
        return data

    def validate_filter(self, data, idx, filters, idx_filter, active_filters):
        tmp_visible = []
        for record in data:
            valid_record = []
            filter_count = 1
            record_count = idx
            while idx_filter - filter_count >= 0:
                if record[record_count + 2] not in filters[idx_filter - filter_count]:
                    valid_record.append(False)
                record_count += 2
                filter_count += 1
            if False not in valid_record:
                tmp_visible.append((record[idx], record[idx + 1]))
        _ids = []
        _filter_ids = []
        for tmp in tmp_visible:
            if tmp not in _ids:
                _ids.append(tmp)
                _filter_ids.append(tmp[0])
        if idx_filter < len(filters):
            if active_filters[idx_filter]:
                filters[idx_filter] = [_id for _id in filters[idx_filter] if _id in _filter_ids]
                if len(filters[idx_filter]) == 0:
                    current = [_id[0] for _id in _ids if 'curr.' in _id[1]]
                    filters[idx_filter] = [current[0]] if len(current) > 0 else [sorted(_ids)[0][0]]
            else:
                filters[idx_filter] = _filter_ids
        else:
            current = [_id[0] for _id in _ids if 'curr.' in _id[1]]
            default_value = [current[0]] if len(current) > 0 else [sorted(_ids)[0][0]]
            filters.append(default_value)
        return sorted(_ids), filters

    def get_tracking_filter(self, filter_workcenter_ids, origin, filters, filters_active, filters_display, period_day=True):
        view_id = self.env['ir.model.data'].get_object('aci_estimation',
                                                       'mrp_timetracking_kanban_view').id
        gantt_view_id = self.env['ir.model.data'].get_object('aci_estimation',
                                                             'mrp_timetracking_gantt_view').id
        data = self.get_filter_data(filter_workcenter_ids, origin)
        # Filter list and visible values
        period_group_ids = []
        period_ids = []
        period_day_ids = []
        department_ids = []
        workcenter_ids = []
        analytic_ids = []
        party_ids = []
        workorder_ids = []

        if data:
            if origin[0] == 'workorder':
                filters_active[5] = False
                filters_active[6] = False
            period_group_ids, filters = self.validate_filter(data, 13, filters, 0, filters_active)
            period_ids, filters = self.validate_filter(data, 11, filters, 1, filters_active)
            period_day_ids, filters = self.validate_filter(data, 9, filters, 2, filters_active)
            if period_day:
                filters[2] = [day[0] for day in period_day_ids]
            department_ids, filters = self.validate_filter(data, 7, filters, 3, filters_active)
            workcenter_ids, filters = self.validate_filter(data, 5, filters, 4, filters_active)
            analytic_ids, filters = self.validate_filter(data, 3, filters, 5, filters_active)
            if origin[0] == 'workorder':
                filters[5] = [an[0] for an in analytic_ids]
            workorder_ids, filters = self.validate_filter(data, 1, filters, 6, filters_active)
            if origin[0] == 'workorder':
                filters[6] = [wo[0] for wo in workorder_ids]
        ids = []

        for record in data:
            if record[1] in filters[6] and\
               record[3] in filters[5] and\
               record[5] in filters[4] and\
               record[7] in filters[3] and\
               record[9] in filters[2] and\
               record[11] in filters[1] and\
               record[13] in filters[0]:
                ids.append(record[0])
        return (view_id, gantt_view_id), filter_workcenter_ids, origin, filters, ids, period_group_ids,\
            period_ids, department_ids, workcenter_ids, analytic_ids, party_ids,\
            workorder_ids, period_day_ids, filters_active, filters_display

    def create_quality_alert(self):
        form_view_id = self.env['ir.model.data'].get_object('aci_estimation', 'quality_alert_view_form_tracking')
        return {
            'name': _('Quality Alert'),
            'res_model': 'quality.alert',
            'type': 'ir.actions.act_window',
            'views': [(form_view_id.id, 'form')],
            'target': 'new',
            'context': {'default_title': 'Tracking: {}'.format(self.product_id.complete_name),
                        'default_product_tmpl_id': self.product_id.product_tmpl_id.id,
                        'default_product_id': self.product_id.id,
                        'default_workcenter_id': self.workcenter_id.id,
                        'default_type': 'production',
                        'default_timetracking_id': self.id}
        }

    def null_button(self):
        return True




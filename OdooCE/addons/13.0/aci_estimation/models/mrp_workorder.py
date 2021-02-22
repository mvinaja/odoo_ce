# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from odoo.exceptions import UserError
from datetime import timedelta, datetime
from odoo.addons import decimal_precision as dp


class MrpWorkorderComponent(models.Model):
    _name = 'mrp.workorder.component'
    _description = 'WorkOrder Component'
    _rec_name = 'product_id'

    product_id = fields.Many2one('product.product')
    party_id = fields.Many2one(related='workorder_id.product_wo.party_id')
    product_tmpl_id = fields.Many2one(related='product_id.product_tmpl_id', readonly=True)
    product_qty = fields.Float('Product Qty.')
    product_uom_id = fields.Many2one(related='product_id.uom_id', readonly=True)
    sequence = fields.Char()
    workorder_id = fields.Many2one('mrp.workorder')
    effective_qty = fields.Float()
    categ_id = fields.Many2one("product.category")
    unit_price = fields.Float()
    component_price = fields.Float()
    wbs_key = fields.Char()

    type = fields.Selection([
        ('bom', 'Bill Of Materials'),
        ('component', 'Components'),
        ('product', 'Raw Materials')
    ], default='product')
    origin = fields.Selection([
        ('bom', 'Bill Of Materials'),
        ('manufacturing', 'Manufacturing')
    ], default='bom')
    bom_id = fields.Many2one('mrp.bom')
    line_id = fields.Many2one('mrp.bom.line')
    explosion_ids = fields.One2many('mrp.workorder.explosion', 'component_id')

    def update_explosion(self, context=None):
        component_ids = self.browse(self.env.context.get('active_ids'))
        component_ids.explode()

    def explode(self):
        Explosion = self.env['mrp.workorder.explosion']
        for _id in self:
            keep_ids = []
            if _id.type == 'product' or _id.type == 'component' and not _id.line_id.child_bom_id:
                explosion_id = self.explosion_ids.filtered(lambda r: r.workorder_id.id == _id.workorder_id.id and
                                                           r.product_id.id == _id.product_id.id)
                if explosion_id:
                    explosion_id.write({
                        'party_id': _id.party_id.id,
                        'categ_id': _id.categ_id.id,
                        'product_qty': _id.product_qty,
                        'standard_price': _id.unit_price,
                        'product_standard_cost': _id.unit_price,
                        'context_price': _id.unit_price,
                        'product_context_cost': _id.unit_price * _id.product_qty
                    })

                else:
                    explosion_id = Explosion.create({
                        'workorder_id': _id.workorder_id.id,
                        'component_id': _id.id,
                        'product_id': _id.product_id.id,
                        'party_id': _id.party_id.id,
                        'categ_id': _id.categ_id.id,
                        'product_qty': _id.product_qty,
                        'standard_price': _id.unit_price,
                        'product_standard_cost': _id.unit_price,
                        'context_price': _id.unit_price,
                        'product_context_cost': _id.unit_price * _id.product_qty
                    })
                keep_ids.append(explosion_id.id)

            else:
                # Bill of material
                if _id.type == 'component':
                    explosion_ids = _id.line_id.child_bom_id.explosion_ids
                else:
                    explosion_ids = _id.bom_id.explosion_ids
                for line_id in explosion_ids.filtered(lambda r: r.type == 'material'):
                    explosion_id = self.explosion_ids.filtered(lambda r: r.workorder_id.id == _id.workorder_id.id and
                                                                         r.product_id.id == line_id.product_id.id)

                    if explosion_id:
                        explosion_id.write({
                            'party_id': line_id.product_id.party_id.id,
                            'categ_id': line_id.product_id.categ_id.id,
                            'product_qty': line_id.product_qty,
                            'standard_price': line_id.context_price,
                            'product_standard_cost': line_id.context_price,
                            'context_price': line_id.context_price,
                            'product_context_cost': line_id.context_price * line_id.product_qty
                        })
                    else:
                        explosion_id = Explosion.create({
                            'workorder_id': _id.workorder_id.id,
                            'component_id': _id.id,
                            'product_id': line_id.product_id.id,
                            'party_id': line_id.product_id.party_id.id,
                            'categ_id': line_id.product_id.categ_id.id,
                            'product_qty': line_id.product_qty,
                            'standard_price': line_id.context_price,
                            'product_standard_cost': line_id.context_price,
                            'context_price': line_id.context_price,
                            'product_context_cost': line_id.context_price * line_id.product_qty
                        })
                    keep_ids.append(explosion_id.id)
            self.explosion_ids.filtered(lambda r: r.id not in keep_ids).unlink()



class MrpWorkorderExplosion(models.Model):
    _name = 'mrp.workorder.explosion'
    _description = 'WorkOrder Explosion'
    _rec_name = 'product_id'

    product_id = fields.Many2one('product.product')
    component_id = fields.Many2one('mrp.workorder.component', ondelete='cascade')
    party_id = fields.Many2one(related='workorder_id.product_wo.party_id')
    product_tmpl_id = fields.Many2one(related='product_id.product_tmpl_id', readonly=True, store=True)
    product_qty = fields.Float('Product Qty.')
    product_uom_id = fields.Many2one(related='product_id.uom_id', readonly=True)
    workorder_id = fields.Many2one('mrp.workorder', ondelete='cascade')
    categ_id = fields.Many2one("product.category")
    standard_price = fields.Float(digits=dp.get_precision('Product Price'), string='Standard Unit Price')
    product_standard_cost = fields.Float(digits=dp.get_precision('Product Price'), string='Standard Product Cost')
    context_price = fields.Float(digits=dp.get_precision('Product Price'), string='Unit Price')
    product_context_cost = fields.Float(digits=dp.get_precision('Product Price'), string='Product Cost')

    product_categ_id = fields.Many2one(related='product_tmpl_id.categ_id')
    sequence = fields.Integer(related='product_id.sequence')
    purchase_ok = fields.Boolean(related='product_tmpl_id.purchase_ok')
    count_seller = fields.Integer(compute='_compute_count_seller')
    warehouse_id = fields.Many2one(related='workorder_id.warehouse_id', store=True)
    production_id = fields.Many2one(related='workorder_id.production_id', store=True)
    baseline_id = fields.Many2one(related='production_id.baseline_id', store=True)
    production_state = fields.Selection(related='production_id.state', string='MO State')
    workcenter_id = fields.Many2one('mrp.workcenter')
    analytic_id = fields.Many2one(related='production_id.project_id', store=True)
    date_required = fields.Datetime(related='workorder_id.date_planned_start', store=True)
    scenario_id = fields.Many2one('lbm.scenario', compute='_compute_scenario')
    period_group_id = fields.Many2one('payment.period.group', compute='_compute_period_group')
    period_id = fields.Many2one('payment.period', compute='_compute_period_group')

    @api.depends('product_id')
    def _compute_count_seller(self):
        Supplier = self.env['product.supplierinfo']
        for r in self:
            r.count_seller = len(Supplier.search([('product_id', '=', r.product_id.id)]))

    @api.depends('baseline_id')
    def _compute_scenario(self):
        for r in self:
            r.scenario_id = r.baseline_id.filtered(lambda y: y.planning_type == 'replanning')

    @api.depends('workorder_id.tworkorder_ids')
    def _compute_period_group(self):
        for r in self:
            period_id = self.env['payment.period'].search([('id', 'in', r.workorder_id.tworkorder_ids.mapped('ite_period_id').ids)],
                                                          order='global_sequence ASC', limit=1)
            r.period_id = period_id.id if period_id else None
            r.period_group_id = r.period_id.group_id.id if period_id else None


class MrpWorkorder(models.Model):
    _inherit = ['mrp.workorder', 'mail.thread', 'mail.activity.mixin']
    _name = 'mrp.workorder'
    _order = 'sequence'

    manual_update = fields.Boolean()
    party_wo_id = fields.Many2one(related='product_wo.party_id')
    analytic_id = fields.Many2one(related='production_id.project_id', string='Analytic ID', store=True)
    analytic_name = fields.Char(related='analytic_id.name', string='Analytic')
    version = fields.Integer(related='operation_id.version')
    warehouse_id = fields.Many2one(related='production_id.context_warehouse')
    component_ids = fields.One2many('mrp.workorder.component', 'workorder_id')
    explosion_ids = fields.One2many('mrp.workorder.explosion', 'workorder_id')
    tracking_duration_expected = fields.Float(compute='_compute_tracking_duration_expected',
                                              string='Duration on Calendar')
    quality_restriction = fields.Boolean()
    quality_restriction_qty = fields.Integer(compute='_compute_quality_restriction_qty')
    production_bom_id = fields.Many2one(related='production_id.bom_id')
    buy_required = fields.Boolean()

    def _get_default_stage_id(self):
        Stage = self.env['mrp.timetracking.stage']
        stage_id = Stage.search([('name', '=', 'ToDo')], limit=1)
        return stage_id.id

    @api.model
    def _read_group_stage_ids(self, stages, domain, order):
        stage_ids = stages._search([])
        return stages.browse(stage_ids)

    baseline_id = fields.Many2one(related='production_id.baseline_id', store=True)
    step_ids = fields.One2many('lbm.work.order.step', 'workorder_id')
    stage_id = fields.Many2one('mrp.timetracking.stage',
        group_expand='_read_group_stage_ids', default=_get_default_stage_id)
    manage_type = fields.Selection([
        ('workorder', 'Workorder Management'),
        ('step', 'Step Management')
    ], string='Management Type', compute='_compute_manage_type', default='step')
    warehouse_id = fields.Many2one(related='production_id.context_warehouse')
    tracking_ids = fields.One2many('mrp.workcenter.productivity', 'workorder_id')
    accum_time = fields.Float('Duration', compute='_compute_duration', default=0, store=True)
    tworkorder_ids = fields.One2many('mrp.timetracking.workorder', 'workorder_id')
    lookahead_active = fields.Boolean(compute='_compute_lookahead_active', store=True, string='In LookAHead')
    active_restriction = fields.Boolean('Active Restrictions', compute='_compute_active_restriction')
    active_restriction_count = fields.Integer('Active Rest. Count', compute='_compute_active_restriction')
    use_restriction = fields.Boolean(default=False)
    can_be_planned = fields.Boolean(compute='_compute_can_be_planned', readonly=False, store=True)
    percent_wo_complete = fields.Float(compute='_compute_percent_complete', string='By WO', compute_sudo=True)
    percent_step_complete = fields.Float(compute='_compute_percent_complete', string='By Step', compute_sudo=True)
    percent_complete = fields.Float(compute='_compute_percent_complete', string='Completed', store=True, compute_sudo=True)
    timetracking_type = fields.Selection([('workorder', 'Workorder'), ('mixed', 'Mixed')],
                                         compute='_compute_timetracking_type', store=True, readonly=False)
    timetracking_ids = fields.One2many('mrp.timetracking', 'workorder_id')
    has_tracking = fields.Boolean(compute='_compute_has_tracking')
    timetracking_active = fields.Boolean(defualt=True)
    has_estimation = fields.Boolean(compute='_compute_has_estimation')

    workstep_extra = fields.Float(compute='_compute_workstep_extra')
    operation_labor = fields.Float('Oper. Crew & Labor')
    crew_amount = fields.Float(
        'Crew Cost', related='operation_id.crew_amount', readonly=True)
    step_duration = fields.Float(compute='_compute_step_duration')
    material_count = fields.Integer(compute='_compute_material_count')
    operation_extra_available = fields.Float(compute='_compute_operation_extra_available')
    product_wo_tmpl = fields.Many2one(related='product_wo.product_tmpl_id', store=True)

    @api.depends('product_wo.product_tmpl_id.quality_restriction_ids')
    def _compute_quality_restriction_qty(self):
        for r in self:
            r.quality_restriction_qty = len(r.product_wo.product_tmpl_id.quality_restriction_ids)

    def compute_operation_data(self, context=None):
        for _id in self:
            _id.operation_labor = sum(_id.step_ids.mapped('labor_cost'))
            self.confirm_workstep()

    def _compute_workstep_extra(self):
        for _id in self:
            extra_value = 0
            for workstep in _id.step_ids.filtered(lambda r: r.add_value):
                extra_value += workstep.duration * workstep.value_factor
            if extra_value:
                _id.workstep_extra = _id.operation_extra / extra_value
            else:
                _id.workstep_extra = 0

    @api.depends('date_planned_start', 'date_planned_finished', 'resource_id.resource_calendar_id')
    def _compute_tracking_duration_expected(self):
        for _id in self:
            if _id.date_planned_start and _id.date_planned_finished:
                tz_date_start = self.env['time.tracking.actions'].get_tz_datetime(
                    _id.date_planned_start, self.env.user)
                tz_date_end = self.env['time.tracking.actions'].get_tz_datetime(
                    _id.date_planned_finished, self.env.user)
                tracking_duration_expected = self.env['lbm.scenario'].get_duration_by_calendar(_id.resource_id.resource_calendar_id,
                                                                                          tz_date_start, tz_date_end)
            else:
                tracking_duration_expected = 0
        _id.tracking_duration_expected = tracking_duration_expected

    def write(self, vals):
        res = super(MrpWorkorder, self).write(vals)
        if 'resource_id' in vals.keys():
            for _id in self:
                _id.step_ids.write({'wkcenter': vals['resource_id']})
        if 'stage_id' in vals:
            for _id in self:
                _id.sync_stage_wo_to_steps(vals['stage_id'])

        if 'product_qty' in vals.keys():
            for _id in self:
                min_qty = sum(_id.tracking_ids.mapped('qty_progress'))
                min_qty = min_qty + sum(_id.step_ids.tracking_ids.filtered(lambda r: r.tracking_origin == 'step').mapped('qty_progress'))
                if vals.get('product_qty') < min_qty:
                    raise ValidationError(_('{} requires at least a qty of {}'.format(res.product_id.complete_name, min_qty)))

        return res

    def unlink(self):
        workstep_ids = self.mapped('step_ids')
        if workstep_ids.mapped('tracking_ids') or self.mapped('tracking_ids'):
            raise ValidationError(_('Cannot remove a workorder with time tracking.'))
        super(MrpWorkorder, self).unlink()

    def name_get(self):
        names = []
        for wo in self:
            if not wo.baseline_id:
                names.append((wo.id, "%s - %s - %s" % (wo.production_id.name, wo.product_id.name, wo.name)))
            else:
                names.append((wo.id, "%s - %s - v.%s" % (wo.product_wo.complete_name, wo.analytic_name, wo.version)))
        return names

    @api.constrains('direct_cost', 'operation_extra')
    def _check_operation_amount(self):
        for _id in self:
            pay_amount = _id.direct_cost + _id.operation_extra
            if pay_amount > _id.operation_labor:
                raise UserError(_('{} pay amount ({}) exceed operation crew & labor ({}).'.format(
                    _id.product_wo.complete_name,
                    pay_amount, _id.direct_cost)))

    @api.depends('operation_id')
    def _compute_manage_type(self):
        for _id in self:
            _id.manage_type = 'step' if _id.operation_id.track_workstep else 'workorder'

    @api.depends('tracking_ids.duration')
    def _compute_duration(self):
        for _id in self:
            _id.accum_time = sum(_id.tracking_ids.filtered(lambda r:  r.tracking_origin == 'workorder').mapped('duration'))/60 or 0

    @api.depends('date_planned_start')
    def _compute_lookahead_active(self):
        today = datetime.now().replace(hour=0, minute=0, second=0)
        start = today - timedelta(days=today.weekday())  # Go to Monday
        start_year = today.year
        for r in self:
            look_ahead = r.production_id.baseline_id.lookahead_window or 0
            end_week = today.isocalendar()[1] + look_ahead - 1
            week_factor = int(end_week / 52)
            end_week = end_week - (52 * week_factor)
            end_year = start_year + week_factor
            end = datetime.strptime('{}-W{}-0'.format(end_year, end_week), "%Y-W%W-%w")
            r.lookahead_active = True if r.date_planned_start and start <= r.date_planned_start <= end else False

    @api.depends('activity_ids', 'activity_ids.activity_source', 'activity_ids.tracking_state')
    def _compute_active_restriction(self):
        for r in self:
            active_restrictions = r.activity_ids.filtered(lambda y: y.activity_source == 'restriction' and
                                                                     y.tracking_state == 'locked' and
                                                                     y.status == 'active')
            r.active_restriction = True if active_restrictions else False
            r.active_restriction_count = len(active_restrictions)

    @api.depends('active_restriction', 'use_restriction', 'baseline_id.type', 'baseline_id')
    def _compute_can_be_planned(self):
        for r in self:
            r.can_be_planned = True if not r.use_restriction else not r.active_restriction

    @api.depends('step_ids', 'qty_production', 'manage_type', 'tracking_ids')
    def _compute_percent_complete(self):
        for r in self:
            r.percent_wo_complete = sum(r.tracking_ids.filtered(lambda y: y.tracking_origin == 'workorder').
                                              mapped('progress'))
            r.percent_step_complete = sum(step_id.percent_wo_complete if step_id.percent_wo_complete < (step_id.tracking_ratio * 100) else
                                          step_id.tracking_ratio * 100 for step_id in r.step_ids)

            r.percent_complete = r.percent_wo_complete + r.percent_step_complete

    @api.depends('baseline_id', 'baseline_id.type')
    def _compute_timetracking_type(self):
        for r in self:
            r.timetracking_type = 'mixed' if r.baseline_id and r.baseline_id.type == 'periodic' else 'workorder'

    @api.depends('time_ids')
    def _compute_has_tracking(self):
        for r in self:
            r.has_tracking = True if len(r.time_ids) >= 1 else False

    @api.depends('step_ids.duration')
    def _compute_step_duration(self):
        for r in self:
            r.step_duration = sum(r.step_ids.mapped('duration'))

    @api.depends('component_ids')
    def _compute_material_count(self):
        for r in self:
            r.material_count = len(r.component_ids)

    @api.depends('operation_extra', 'step_ids', 'tracking_ids')
    def _compute_operation_extra_available(self):
        for r in self:
            used_operation_extra = sum(r.tracking_ids.filtered(lambda y: y.tracking_origin == 'workorder').mapped('operation_extra')) \
                                   + sum(r.step_ids.tracking_ids.filtered(lambda y: y.tracking_origin == 'step').mapped('operation_extra'))
            r.operation_extra_available = r.operation_extra - used_operation_extra

    def action_open_wizard(self):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id("mrp.mrp_workorder_mrp_production_form")
        action['res_id'] = self.id
        action['target'] = 'current'
        return action

    def add_workstep_btn(self):
        action = self.env.ref('aci_estimation.add_workorder_step_wizard_action').read()[0]
        return action

    def export_workstep_btn(self):
        action = self.env.ref('aci_estimation.copy_workorder_step_wizard_action').read()[0]
        action['context'] = {'default_source_workorder': self.id}
        return action

    def show_material_btn(self):
        self.ensure_one()
        view_id = self.env['ir.model.data'].get_object(
            'aci_estimation', 'mrp_workorder_component_tree_view')
        return {
            'type': 'ir.actions.act_window',
            'name': 'Components',
            'view_type': 'form',
            'view_mode': 'tree, form',
            'res_model': 'mrp.workorder.component',
            'views': [[view_id.id, "tree"]],
            'domain': [('id', 'in', self.component_ids.ids)],
            'target': 'current',
        }

    def show_quality_btn(self):
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
            'domain': [('product_tmpl_id', '=', self.product_wo.product_tmpl_id.id)],
            'context': {'default_product_tmpl_id': self.product_wo.product_tmpl_id.id}
        }

    def button_detailed_form(self):
        self.ensure_one()
        view_id = self.env['ir.model.data'].get_object(
            'mrp', 'mrp_production_workorder_form_view_inherit')
        return {
            'res_model': 'mrp.workorder',
            'res_id': self.id,
            'type': 'ir.actions.act_window',
            'view_id': view_id.id,
            'view_type': 'form',
            'view_mode': 'form',
            'target': 'current'
        }

    def button_quality_alert(self):
        view_form_id = self.env['ir.model.data'].get_object(
            'aci_estimation', 'quality_alert_view_form_tracking')
        view_id = self.env['ir.model.data'].get_object(
            'quality_control', 'quality_alert_view_kanban')

        analytic_id = self._context.get('selected_analytic_id')
        default_analytic_id = analytic_id if analytic_id else None
        return {
            'name': _('Assign Quality Work Center'),
            'res_model': 'quality.alert',
            'type': 'ir.actions.act_window',
            'views': [(view_id.id, 'kanban'), (view_form_id.id, 'form')],
            'target': 'current',
            'context': {'default_workcenter_id': self.resource_id.id,
                        'default_product_tmpl_id': self.product_wo.product_tmpl_id.id,
                        'default_activity_product_id': self.product_wo.id,
                        'default_type': 'production',
                        'default_analytic_id': default_analytic_id},
            'domain': [('id', 'in', self.env['quality.alert'].search([('product_id', '=', self.product_wo.id),
                                                                      ('workcenter_id', '=',
                                                                       self.resource_id.id)]).ids)]
        }

    def show_tracking(self):
        self.ensure_one()
        view_id = self.env['ir.model.data'].get_object(
            'aci_estimation', 'mrp_workorder_tracks_form_view')
        context = {'is_readonly': True, 'form_kanban': False}

        return {
            'name': '{0}: {1}'.format(_('Time Tracking'), self.product_id.name_get()[0][1]),
            'res_model': 'mrp.workorder',
            'res_id': self.id,
            'type': 'ir.actions.act_window',
            'view_id': view_id.id,
            'view_type': 'form',
            'view_mode': 'form',
            'context': context,
            'target': 'new'
        }

    def _get_time_block(self, calendar_id, date_start, date_end):
        time_block = []
        _origin_start = date_start
        while date_start.strftime('%Y-%m-%d') <= (date_end + timedelta(days=30)).strftime('%Y-%m-%d'):
            for att in calendar_id.attendance_ids.filtered(lambda r: r.dayofweek == str(date_start.weekday())):
                from_hour = int('{0:02.0f}'.format(*divmod(att.hour_from * 60, 60)))
                from_minutes = int('{1:02.0f}'.format(*divmod(att.hour_from * 60, 60)))
                to_hour = int('{0:02.0f}'.format(*divmod(att.hour_to * 60, 60)))
                to_minutes = int('{1:02.0f}'.format(*divmod(att.hour_to * 60, 60)))

                _start = date_start.replace(hour=from_hour, minute=from_minutes, second=0)
                _end = date_start.replace(hour=to_hour, minute=to_minutes, second=0)

                if _start < _origin_start <= _end:
                    _start = _origin_start

                if _end > _origin_start:
                    time_block.append({'start': _start, 'end': _end,
                                      'duration': (_end-_start).total_seconds() / 60})
            date_start = (date_start + timedelta(days=1)).replace(hour=0, minute=0, second=1)
        return time_block

    def _get_date_by_calendar(self, time_block, date_start, missing_duration):
        date = None
        for block in time_block:
            if block['end'] >= date_start:
                if block['start'] < date_start:
                    block.update({'start': date_start, 'duration': (block['end']-date_start).total_seconds() / 60})

                if block['duration'] >= missing_duration:
                    date = block['start'] + timedelta(minutes=missing_duration)
                    break
                else:
                    missing_duration = missing_duration - block['duration']
        return date

    def confirm_workstep(self):
        for r in self.filtered(lambda y: y.manual_update is False or not y.step_ids):
            # Map new workstep data
            workstep_data = {}
            operation_id = r.operation_id
            manufacture_type = r.production_id.baseline_id.type
            if r.operation_id.track_workstep:
                for workstep in operation_id.bom_line_ids.filtered(lambda r: r.type == 'workstep'):
                    ratio = 1 if manufacture_type in ('periodic', 'operational') else workstep.duration * 60 / operation_id.duration if operation_id.duration else 0
                    workstep_data[workstep.product_id.id] = {
                        'sequence': workstep.sequence,
                        'product_id': workstep.product_id.id,
                        'workstep_id': workstep.id,
                        'wkcenter': r.resource_id.id,
                        'net_cost': workstep.product_qty and workstep.labor_cost / workstep.product_qty or 0,
                        'extra_cost': workstep.product_qty and workstep.extra_cost / workstep.product_qty or 0,
                        'ratio': ratio,
                        'rate': workstep.rate,
                        'rate_uom': workstep.product_uom_id.id,
                        'time_uom': workstep.time_uom.id,
                        'product_qty': workstep.product_qty
                    }
                # Map former worksteps
                former_steps = {}
                for workstep in r.step_ids:
                    former_steps[workstep.product_id.id] = workstep

                # Compare former and new data
                workstep_cmds = []
                for key, vals in workstep_data.items():

                    # Get former workstep
                    workstep_id = former_steps.pop(key, False)

                    # Evaluate if workstep already exists
                    if not workstep_id:
                        # No, create a new record
                        vals['stage_id'] = self.env.ref('aci_estimation.aci_stop_stage').id
                        workstep_cmds.append((0, False, vals))

                    else:
                        # Yes, update values

                        self.clean_working_timer(workstep_id.id)

                        vals['stage_id'] = self._change_workstep_stage(workstep_id.stage_id.name)
                        if workstep_id.tracking_ids:
                            min_product_qty = sum(workstep_id.tracking_ids.mapped('qty_progress'))
                            if vals['product_qty'] < min_product_qty:
                                raise ValidationError(
                                    _('{} requires at least a qty of {}'.format(workstep_id.product_id.complete_name,
                                                                                min_product_qty)))
                        workstep_cmds.append((1, workstep_id.id, vals))

                # Delete removed worksteps
                for workstep in filter(lambda r: not r.tracking_ids, former_steps.values()):
                    if workstep.has_tracking:
                        workstep.timetracking_active = False
                    else:
                        workstep_cmds.append((2, workstep.id, False))
                r.write({'step_ids': workstep_cmds})

        for r in self:
            r.confirm_component()
            r.confirm_explosion()
            input_ids = self.env['mrp.workcenter.productivity'].search([('workorder_by_step', '=', r.id)])
            if not input_ids:
                r.step_ids.write({'do_tracking': True})

    def confirm_component(self):
        component_data = {}
        component_ids = []

        component_ids.append({'factor': self.qty_production,
                              'data': self.operation_id.material_ids})

        for component in component_ids:
            factor = component['factor']
            for data in component['data']:
                product_qty = data.product_qty * factor
                effective_qty = data.effective_qty * factor
                if data.product_id.id in component_data:
                    component_data[data.product_id.id].update({'product_qty': component_data[data.product_id.id]['product_qty']
                                                                                   + product_qty,
                                                               'effective_qty': component_data[data.product_id.id]['effective_qty']
                                                                                   + effective_qty})
                else:
                    component_data[data.product_id.id] = {
                        'product_id': data.product_id.id,
                        'sequence': data.sequence,
                        'wbs_key': data.wbs_key,
                        'party_id': data.party_id.id,
                        'categ_id': data.categ_id.id,
                        'product_qty': product_qty,
                        'effective_qty': effective_qty,
                        'unit_price': data.unit_price,
                        'component_price': data.component_price
                    }

        # Map former components
        former_components = {}
        for component in self.component_ids.filtered(lambda r: r.origin == 'bom'):
            former_components[component.product_id.id] = component

        # Compare former and new data
        cmds = []
        for key, vals in component_data.items():

            # Get former component
            component_id = former_components.pop(key, False)

            # Evaluate if component already exists
            if not component_id:
                # No, create a new record
                cmds.append((0, False, vals))

            else:
                cmds.append((1, component_id.id, vals))

        # Delete removed component
        for component in former_components.values():
            cmds.append((2, component.id, False))
        self.write({'component_ids': cmds})

    def confirm_explosion(self):
        Explosion = self.env['mrp.bom.explosion']
        explosion_data = {}
        explosion_ids = []
        if self.manual_update is False:
            explosion_ids.append({'factor': self.qty_production,
                                  'data': Explosion.search([('bom_id', '=', self.operation_id.id)]).filtered(lambda r: r.type == 'material')})

        else:
            for step_id in self.step_ids:
                explosion_ids.append({'factor': step_id.product_qty,
                                     'data': Explosion.search([('bom_id', '=', step_id.workstep_id.child_bom_id.id)]).filtered(lambda r: r.type == 'material')})

        for explosion in explosion_ids:
            factor = explosion['factor']
            for data in explosion['data']:
                if data.product_id.id in explosion_data:
                    product_qty = data.product_qty * factor
                    explosion_data[data.product_id.id].update({'product_qty': explosion_data[data.product_id.id]['product_qty']
                                                                                   + product_qty})
                else:
                    ctx = self.env['ir.property'].search([('context_bom', '=', self.operation_id.context_bom.id),
                                                          ('name', '=', 'context_price'),
                                                          ('res_id', '=',  'product.product,{}'.format(data.product_id.id))], limit=1)
                    product_qty = data.product_qty * factor
                    explosion_data[data.product_id.id] = {
                        'product_id': data.product_id.id,
                        'party_id': data.product_id.party_id.id,
                        'categ_id': data.product_id.categ_id.id,
                        'product_qty': product_qty,
                        'standard_price': float(ctx.value_float or 0.0),
                        'product_standard_cost': float(ctx.value_float or 0.0),
                        'context_price': float(ctx.value_float or 0.0),
                        'product_context_cost': float(ctx.value_float or 0.0) * product_qty
                    }

        # Map former explosions
        former_explosions = {}
        for explosion in self.explosion_ids:
            former_explosions[explosion.product_id.id] = explosion

        # Compare former and new data
        cmds = []
        for key, vals in explosion_data.items():

            # Get former explosion
            explosion_id = former_explosions.pop(key, False)

            # Evaluate if explosion already exists
            if not explosion_id:
                # No, create a new record
                cmds.append((0, False, vals))

            else:
                cmds.append((1, explosion_id.id, vals))

        # Delete removed explosion
        for explosion in former_explosions.values():
            cmds.append((2, explosion.id, False))
        self.write({'explosion_ids': cmds})

    def clean_working_timer(self, step_id):
        step_tracking_ids = self.env['mrp.workcenter.productivity'].search([('step_id', '=', step_id),
                                                                            ('date_end', '=', None)])
        for step in step_tracking_ids:
            wo_tracking_id = self.env['mrp.workcenter.productivity'].search([('key', '=', step.key_diff)])
            wo_tracking_id.unlink()
        step_tracking_ids.unlink()

    def _change_workstep_stage(self, current_stage):
        stages_conversion = {
            'ToDo': 'ToDo',
            'Working': 'ToDo',
            'Blocked': 'ToDo',
            'Finished': 'Finished',
            'Cancel': 'ToDo'
        }

        stage_id = self.env['mrp.timetracking.stage'].search([('name', '=', stages_conversion[current_stage])], limit=1)
        return stage_id.id

    def sync_stage_wo_to_steps(self, new_stage):
        self.ensure_one()
        if self.manage_type == 'workorder':
            step_updates = self.step_ids.mapped(lambda r: (1, r.id, {'stage_id': new_stage}))
            self.write({'step_ids': step_updates})

    def delete_tracking_btn(self):
        todo_stage_id = self.env['time.tracking.actions'].get_stage_id('ToDo')
        self.env['mrp.workcenter.productivity'].search([('workorder_id', '=', self.id)]).unlink()
        self.env['mrp.timetracking'].search([('workorder_id', '=', self.id)]).write({'stage_id': todo_stage_id})

    def _compute_has_estimation(self):
        estimation_ids = self.env['mrp.estimation'].search([('estimation_type', '=', 'period')])
        for r in self:
            has_estimation = False
            for estimation_id in estimation_ids:
                if r.id in estimation_id.timetracking_ids.mapped('workorder_id').ids:
                    has_estimation = True
                    break
            r.has_estimation = has_estimation

    def show_estimation_btn(self):
        view_id = self.env['ir.model.data'].get_object(
            'aci_estimation', 'mrp_estimation_tree_view')

        estimation_ids = self.env['mrp.estimation'].search([('estimation_type', '=', 'period')])
        _ids = []
        for estimation_id in estimation_ids:
            if self.id in estimation_id.timetracking_ids.mapped('workorder_id').ids:
                _ids.append(estimation_id.id)
        return {
            'type': 'ir.actions.act_window',
            'name': 'Estimation',
            'views': [(view_id.id, 'tree'), (False, 'form')],
            'res_model': 'mrp.estimation',
            'domain': [('id', 'in', _ids)],
            'target': 'current'
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
            'context': {'product_id': self.product_wo.product_tmpl_id.id}
        }

    def change_quality_restriction_btn(self, context=None):
        context = self.env.context
        for workorder_id in self.browse(context.get('active_ids')):
            workorder_id.quality_restriction = not workorder_id.quality_restriction
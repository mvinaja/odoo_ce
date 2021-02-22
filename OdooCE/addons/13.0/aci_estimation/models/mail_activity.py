from odoo import api, exceptions, fields, models, _
from odoo.exceptions import UserError
from odoo.http import request
from datetime import datetime

from odoo.tools import DEFAULT_SERVER_DATE_FORMAT


class MailActivity(models.Model):
    _inherit = 'mail.activity'
    _description = 'Activity'

    activity_source = fields.Selection([('normal', 'Normal'),
                                        ('restriction', 'Restriction'),
                                        ('noncompliance', 'Noncompliance'),
                                        ('nonconformity', 'Nonconformity'),
                                        ('pending', 'Pendings')], default='normal')
    category_id = fields.Many2one('product.category', 'Category')
    product_id = fields.Many2one('product.product')
    department_id = fields.Many2one('hr.department', string="Department")
    workcenter_id = fields.Many2one('mrp.workcenter')
    workcenter_ids = fields.Many2many('mrp.workcenter', 'mrp_activity_workcenter_rel', 'activity_id', 'workcenter_id', string='Workcenters')
    res_analytic_id = fields.Many2one('account.analytic.account', compute='_compute_res_analytic_id',
                                  string='Res Analytic', ondelete='restrict', store=True)
    manual_analytic_id = fields.Many2one('account.analytic.account', string='Manual Analytic', ondelete='restrict')
    analytic_id = fields.Many2one('account.analytic.account',  compute='_compute_analytic_id',
                                  string='Analytic Account', store=True)
    assign_string = fields.Char(compute='_compute_assign_string')
    status = fields.Selection([('draft', 'Draft'), ('active', 'Active')], compute='_compute_status')
    tracking_state = fields.Selection([('unlocked', 'Unlocked'), ('locked', 'Locked')], default='locked')
    activity_icon = fields.Char('Activity Icon', help="Font awesome icon e.g. fa-tasks")
    on_tracking_step = fields.Boolean(compute='_compute_on_tracking')
    on_tracking_wo = fields.Boolean(compute='_compute_on_tracking')
    on_tracking_activity = fields.Boolean(compute='_compute_on_tracking')
    proposed_date = fields.Date()
    solved_date = fields.Date()

    @api.model
    def default_get(self, fields):
        res = super(MailActivity, self).default_get(fields)
        activity_type = self.env['mail.activity.type'].search([('name', '=', 'To Do')])
        res['activity_type_id'] = activity_type.id

        model_id = self.env['ir.model'].search([('model', '=', self._context.get('default_res_model'))])
        fields = self.env['ir.model.fields'].sudo().search([('model_id', '=', model_id.id),
                                                            ('relation', '=', 'mrp.workcenter'),
                                                            ('ttype', 'in', ('many2one', 'many2many'))])

        if fields:
            workcenter_id = None
            for field in fields:
                record = self.env[model_id.model].browse([self._context.get('default_res_id')])
                if record[field.name] and field.ttype == 'many2one':
                    workcenter_id = record[field.name]
                elif record[field.name]:
                    workcenter_id = record[field.name][0]
            if workcenter_id:
                res['workcenter_ids'] = [(6, 0, [workcenter_id.id])]
                res['department_id'] = workcenter_id.department_id.id

        return res

    @api.model
    def create(self, vals):
        if request.session.get('session_workcenter'):
            vals['workcenter_id'] = request.session.get('session_workcenter')

        if 'date_deadline' in vals and 'proposed_date' not in vals:
            vals['proposed_date'] = vals.get('date_deadline')

        if vals.get('activity_source') in ('restriction', 'noncompliance', 'nonconformity'):
            datetime_deadline = datetime.combine(
                datetime.strptime(vals.get('date_deadline'), DEFAULT_SERVER_DATE_FORMAT), datetime.min.time())
            search_args = [('res_id', '=', vals.get('res_id')),
                           ('res_model_id', '=', vals.get('res_model_id')),
                           ('product_id', '=', vals.get('product_id')),
                           ('analytic_id', '=', vals.get('final_analytic_id')),
                           ('date_deadline', '=', datetime_deadline)]
        if vals.get('activity_source') == 'restriction':
            vals['activity_icon'] = 'fa-lock'
            activity_id = self.search(search_args + [('activity_source', '=', 'restriction')])
            if activity_id:
                raise UserError(_("You already have an activity on this record with the same configuration."))
        elif vals.get('activity_source') == 'noncompliance':
            vals['activity_icon'] = 'fa-warning'
            activity_id = self.search(search_args + [('activity_source', '=', 'noncompliance')])
            if activity_id:
                raise UserError(_("You already have an activity on this record with the same configuration."))
        elif vals.get('activity_source') == 'nonconformity':
            vals['activity_icon'] = 'fa-exclamation-circle'
            activity_id = self.search(search_args + [('activity_source', '=', 'nonconformity')])
            if activity_id:
                raise UserError(_("You already have an activity on this record with the same configuration."))
        return super(MailActivity, self).create(vals)

    def unlink(self):
        for activity in self:
            if activity.activity_source == 'restriction' and activity.tracking_state == 'locked' and activity.status == 'active':
                raise UserError(_('In order to delete an active restriction, you must first unlock it.'))
        return super(MailActivity, self).unlink()

    @api.onchange('activity_source')
    def onchange_activity_source(self):
        self.category_id = None
        self.product_id = None
        valid = True
        if self.activity_source == 'restriction':
            field_name = 'is_restriction'
        elif self.activity_source == 'noncompliance':
            field_name = 'is_noncompliance'
        elif self.activity_source == 'nonconformity':
            field_name = 'is_nonconformity'
        elif self.activity_source == 'pending':
            field_name = 'is_pending'
        else:
            valid = False
        if valid:
            categ_ids = self.env['product.product'].search([(field_name, '=', True)]).mapped('categ_id').ids
            if categ_ids:
                self.category_id = categ_ids[0]
            return {
                'domain': {
                    'category_id': [('id', 'in', categ_ids)],
                }
            }

    @api.onchange('category_id')
    def onchange_category_id(self):
        self.product_id = None

        valid = True
        if self.activity_source == 'restriction':
            field_name = 'is_restriction'
        elif self.activity_source == 'noncompliance':
            field_name = 'is_noncompliance'
        elif self.activity_source == 'nonconformity':
            field_name = 'is_nonconformity'
        elif self.activity_source == 'pending':
            field_name = 'is_pending'
        else:
            valid = False

        if valid:
            search_args = [('bom_type', 'in', ('basic', 'workorder')), ('categ_id', '=', self.category_id.id),
                           (field_name, '=', True)]
            if self.activity_source == 'restriction':
                search_args.append(('is_restriction', '=', True))
            elif self.activity_source == 'noncompliance':
                search_args.append(('is_noncompliance', '=', True))
            elif self.activity_source == 'nonconformity':
                search_args.append(('is_nonconformity', '=', True))
            product_ids = self.env['product.product'].search(search_args).ids
            if product_ids:
                self.product_id= product_ids[0]
            return {
                'domain': {
                    'product_id': [('id', 'in', product_ids)],
                }
            }

    @api.onchange('tracking_state')
    def onchange_tracking_state(self):
        if self.tracking_state == 'unlocked':
            workcenter_id = self.env['mrp.workcenter'].browse([request.session.get('session_workcenter')])
            if not workcenter_id:
                workcenter_id = self.env['mrp.workcenter'].search([('employee_id.user_id', '=', self.env.user.id)],
                                                                  limit=1)
            if workcenter_id:
                self.department_id = workcenter_id.employee_id.department_id.id
                self.workcenter_ids = [(6, False, [workcenter_id.id])]

    @api.depends('res_model_id', 'res_model', 'res_id')
    def _compute_res_analytic_id(self):
        for r in self:
            field_ids = self.env['ir.model.fields'].sudo().search([('model_id', '=', r.res_model_id.id),
                                                                   ('relation', '=', 'account.analytic.account'),
                                                                   ('ttype', 'in', ('many2one', 'many2many'))])
            analytic_id = None
            if field_ids:
                for field in field_ids:
                    record = self.env[r.res_model].browse([r.res_id])
                    if record[field.name] and field.ttype == 'many2one':
                        analytic_id = record[field.name].id
                    elif record[field.name]:
                        analytic_id = record[field.name][0].id
            r.res_analytic_id = analytic_id

    @api.depends('res_analytic_id', 'manual_analytic_id')
    def _compute_analytic_id(self):
        for r in self:
            r.analytic_id = r.manual_analytic_id.id if r.manual_analytic_id else r.res_analytic_id.id

    @api.depends('workcenter_ids', 'activity_source', 'user_id')
    def _compute_assign_string(self):
        for r in self:
            r.assign_string = r.user_id.name if r.activity_source == 'normal' else ','.join(r.workcenter_ids.mapped('code'))

    @api.depends('workcenter_ids', 'product_id')
    def _compute_on_tracking(self):
        Tracking = self.env['mrp.timetracking']
        for r in self:
            if r.product_id and r.workcenter_ids:
                args = [('workcenter_id', 'in', r.workcenter_ids.ids), ('product_id', '=', r.product_id.id)]
                tracking_step_ids = Tracking.search(args + [('tracking_origin', '=', 'step')])
                tracking_wo_ids = Tracking.search(args + [('tracking_origin', '=', 'workorder')])
                tracking_activity_ids = Tracking.search(args + [('tracking_origin', '=', 'activity')])
            else:
                tracking_step_ids = False
                tracking_wo_ids = False
                tracking_activity_ids = False
            r.on_tracking_step = True if tracking_step_ids else False
            r.on_tracking_wo = True if tracking_wo_ids else False
            r.on_tracking_activity = True if tracking_activity_ids else False

    def _compute_status(self):
        Tracking = self.env['mrp.timetracking']
        for r in self:
            tracking_step_ids = None
            tracking_wo_ids = None
            tracking_activity_ids = None
            if r.product_id and r.workcenter_ids:
                args = [('workcenter_id', 'in', r.workcenter_ids.ids), ('product_id', '=', r.product_id.id)]
                tracking_step_ids = Tracking.search(args + [('tracking_origin', '=', 'step')])
                tracking_wo_ids = Tracking.search(args + [('tracking_origin', '=', 'workorder')])
                tracking_activity_ids = Tracking.search(args + [('activity_id', '=', r.id)])
            r.status = 'active' if tracking_step_ids or tracking_wo_ids or tracking_activity_ids else 'draft'

    def activity_tree_btn(self, condition, model, res_id):
        if condition == 'all':
            _ids = self.env[model].browse([res_id]).activity_ids.ids
        else:
            _ids = self.env[model].browse([res_id]).activity_ids.filtered(lambda r: r.activity_source == condition).ids
        view_id = self.env['ir.model.data'].get_object(
            'aci_estimation', 'mail_activity_tree_view')
        return {
            'name': _(condition + ' activity'),
            'res_model': 'mail.activity',
            'type': 'ir.actions.act_window',
            'views': [(view_id.id, 'list')],
            'target': 'current',
            'domain': [('id', 'in', _ids)],
            'context': self._context,
        }

    def activity_configurator_btn(self, model, res_id):
        model_id = self.env['ir.model'].sudo().search([('model', '=', model)])
        res_id = self.env[model].browse([res_id])
        context = self.env.context.copy()
        context.update({
            'active_ids': None,
            'default_res_ids': [(0, False, {'res_model_id': model_id.id,
                                            'res_model': model_id.model,
                                            'res_id': res_id.id,
                                            'res_name': res_id.name})]
        })
        view_id = self.env['ir.model.data'].get_object(
            'aci_estimation', 'mail_activity_configurator_form_view')
        return {
            'type': 'ir.actions.act_window',
            'views': [(view_id.id, 'form')],
            'res_model': 'mail.activity.configurator',
            'name': 'Activity Configurator',
            'target': 'new',
            'context': context
        }

    def create_tracking_btn(self):
        datetime_deadline = datetime.combine(self.date_deadline, datetime.min.time())
        cmds = []
        analytic_id = self.analytic_id.id
        count = 1
        if analytic_id:
            for workcenter_id in self.workcenter_ids:
                tracking_id = self.env['mrp.timetracking'].search([('analytic_id', '=', analytic_id),
                                                                   ('activity_product_id', '=', self.product_id.id),
                                                                   ('activity_workcenter_id', '=', workcenter_id.id),
                                                                   ('tracking_origin', '=', 'activity'),
                                                                   ('date_start', '=', self.create_date),
                                                                   ('date_end', '=', datetime_deadline)])
                if not tracking_id:
                    period_id = self.env['payment.period'].search([('group_id', '=', workcenter_id.period_group_id.id),
                                                                   ('to_date', '>=', datetime_deadline),
                                                                   ('from_date', '<=', datetime_deadline)])
                    tracking_cmd = {'activity_id': self.id,
                                    'baseline_id': None,
                                    'production_id': None,
                                    'workorder_id': None,
                                    'step_id': None,
                                    'analytic_id': analytic_id,
                                    'tracking_origin': 'activity',
                                    'period_group_id': workcenter_id.period_group_id.id,
                                    'planned_period_id': period_id.id,
                                    'activity_workcenter_id': workcenter_id.id,
                                    'activity_product_id': self.product_id.id,
                                    'expected_qty': 1,
                                    'estimation_type': 'period',
                                    'date_start': self.create_date,
                                    'date_end': datetime_deadline,
                                    'month_number': 0,
                                    'day_number': 0,
                                    'key': '0.0.0.0.{}.{}.0.{}'.format(period_id.id, analytic_id, count)}
                    cmds.append(tracking_cmd)
                    count += 1
        self.env['mrp.timetracking'].create(cmds)

    def show_tracking_action(self, result, tracking_type):
        view_id = result[0][0]
        gantt_view_id = result[0][1]
        display_name = 'tracking by {}'.format(tracking_type)
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
            'is_supervisor': True if len(self.workcenter_ids.ids) > 1 else False
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
        return action

    def show_tracking_step_btn(self):
        workcenter_id = self.env['mrp.workcenter'].search([('employee_id.user_id', '=', self.env.user.id)], limit=1)
        if workcenter_id:
            request.session['session_workcenter'] = workcenter_id.id
        result = self.env['mrp.timetracking'].get_tracking_filter(self.workcenter_ids.ids, ['step', 'building', False, self.product_id.id, False, None, None], [], [True] * 7, [True] * 7)
        if not result[3]:
            result = self.env['mrp.timetracking'].get_tracking_filter(self.workcenter_ids.ids, ['step', 'periodic', False, self.product_id.id, False, None, None], [], [True] * 7, [True] * 7)
        if not result[3]:
            raise UserError(_('Error retrieving tracking records'))
        return self.show_tracking_action(result, 'step')

    def show_tracking_wo_btn(self):
        if not request.session.get('session_workcenter'):
            workcenter_id = self.env['mrp.workcenter'].search([('employee_id.user_id', '=', self.env.user.id)], limit=1)
            if workcenter_id:
                request.session['session_workcenter'] = workcenter_id.id
        result = self.env['mrp.timetracking'].get_tracking_filter(self.workcenter_ids.ids, ['workorder', 'building', False, self.product_id.id, False, None, None], [], [True] * 7, [True] * 7)
        if not result[3]:
            result = self.env['mrp.timetracking'].get_tracking_filter(self.workcenter_ids.ids, ['workorder', 'periodic', False, self.product_id.id, False, None, None], [], [True] * 7, [True] * 7)
        if not result[3]:
            raise UserError(_('Error retrieving tracking records'))
        return self.show_tracking_action(result, 'workorder')

    def show_tracking_activity_btn(self):
        workcenter_id = self.env['mrp.workcenter'].search([('employee_id.user_id', '=', self.env.user.id)], limit=1)
        if workcenter_id:
            request.session['session_workcenter'] = workcenter_id.id
        result = self.env['mrp.timetracking'].get_tracking_filter(self.workcenter_ids.ids, ['activity', 'building', False, self.product_id.id, False, None, None], [], [True] * 7, [True] * 7)
        if not result[3]:
            result = self.env['mrp.timetracking'].get_tracking_filter(self.workcenter_ids.ids, ['activity', 'periodic', False, self.product_id.id, False, None, None], [], [True] * 7, [True] * 7)
        if not result[3]:
            raise UserError(_('Error retrieving tracking records'))
        return self.show_tracking_action(result, 'activity')

    def solve_activity_btn(self, context=None):
        context = self.env.context
        self.browse(context.get('active_ids')).write({'tracking_state': 'unlocked',
                                                      'solved_date': datetime.today().strftime(DEFAULT_SERVER_DATE_FORMAT)})



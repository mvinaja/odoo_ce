# -*- coding: utf-8 -*-

from odoo import models, fields, api
from odoo.http import request


class MailActivityConfigurator(models.TransientModel):
    _name = 'mail.activity.configurator'
    _description = 'mail.activity.configurator'

    # source_res_model_id = fields.Many2one('ir.model')
    res_ids = fields.One2many('mail.activity.configurator.res', 'configurator_id', string='Records')
    activity_ids = fields.One2many('mail.activity.configurator.activity', 'configurator_id', string='Activity')
    # Activity Records
    user_id = fields.Many2one(
        'res.users', 'Assigned to',
        default=lambda self: self.env.user,
        index=True, required=True, ondelete='cascade')
    activity_type_id = fields.Many2one('mail.activity.type', string='Activity Type')
    summary = fields.Char('Summary')
    date_deadline = fields.Date('Due Date', index=True, required=True, default=fields.Date.context_today)
    activity_source = fields.Selection([('normal', 'Normal'),
                                        ('restriction', 'Restriction'),
                                        ('noncompliance', 'Noncompliance'),
                                        ('nonconformity', 'Nonconformity')], default='restriction')
    category_id = fields.Many2one('product.category', 'Category')
    product_id = fields.Many2one('product.product')
    department_id = fields.Many2one('hr.department', string="Department")
    workcenter_id = fields.Many2one('mrp.workcenter')
    workcenter_ids = fields.Many2many('mrp.workcenter', 'mrp_activity_workcenter_conf_rel', 'activity_id', 'workcenter_id')
    analytic_id = fields.Many2one('account.analytic.account', string='Analytic Account')
    note = fields.Html('Note')
    tracking_state = fields.Selection([('unlocked', 'Unlocked'), ('locked', 'Locked')], default='locked', string='State')
    send_to_tracking = fields.Boolean(default=False)

    @api.model
    def default_get(self, fields):
        res = super(MailActivityConfigurator, self).default_get(fields)
        ConfRes = self.env['mail.activity.configurator.res']
        context = self._context
        ids = context.get('active_ids', [])
        res_model = context.get('source_res_model')
        if res_model and ids:
            # Hack for lbm.workorder
            if res_model in ('lbm.workorder', 'mrp.timetracking.workorder', 'mrp.timetracking.workorder'):
                ids = self.env[res_model].browse(ids).mapped('workorder_id').ids
                res_model = 'mrp.workorder'

            res_model_id = self.env['ir.model'].sudo().search([('model', '=', res_model)]).id
            _ids = [ConfRes.create({'res_id': res_id, 'res_model_id': res_model_id}).id for res_id in ids]
            res['res_ids'] = [(6, 0, _ids)]
        activity_type = self.env['mail.activity.type'].search([('name', '=', 'To Do')])
        res['activity_type_id'] = activity_type.id if activity_type else None
        return res

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
        else:
            valid = False
        if valid:
            categ_ids = self.env['product.product'].search([(field_name, '=', True)]).mapped('categ_id').ids
            return {
                'domain': {
                    'category_id': [('id', 'in', categ_ids)],
                }
            }

    @api.onchange('category_id')
    def onchange_category_id(self):
        self.product_id = None
        search_args = [('bom_type', 'in', ('basic', 'workorder')), ('categ_id', '=', self.category_id.id)]
        if self.activity_source == 'restriction':
            search_args.append(('is_restriction', '=', True))
        elif self.activity_source == 'noncompliance':
            search_args.append(('is_noncompliance', '=', True))
        elif self.activity_source == 'nonconformity':
            search_args.append(('is_nonconformity', '=', True))
        product_ids = self.env['product.product'].search(search_args).ids
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

    def reset_record_btn(self):
        self.res_ids.unlink()
        return self.reload()

    def reset_activity_btn(self):
        self.activity_ids.unlink()
        return self.reload()

    def reload(self, view_id=None):
        context = self.env.context.copy()
        context.update({
            'active_ids': None,
            'default_res_ids': [(6, False, self.res_ids.ids)],
            'default_activity_ids': [(6, False, self.activity_ids.ids)],
            'default_user_id': self.user_id.id,
            'default_activity_type_id': self.activity_type_id.id,
            'default_summary': self.summary,
            'default_date_deadline': self.date_deadline,
            'default_activity_source': self.activity_source,
            'default_category_id': self.category_id.id,
            'default_product_id': self.product_id.id,
            'default_department_id': self.department_id.id,
            'default_workcenter_id': self.workcenter_id.id,
            'default_workcenter_ids': [(6, False, self.workcenter_ids.ids)],
            'default_analytic_id': self.analytic_id.id,
            'default_note': self.note,
            'default_tracking_state': self.tracking_state,
            'default_send_to_tracking': self.send_to_tracking
        })
        if not view_id:
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

    def load_text_view_btn(self):
        view_id = self.env['ir.model.data'].get_object(
            'aci_estimation', 'mail_activity_configurator_text_form_view')
        return self.reload(view_id)

    def go_back_btn(self):
        return self.reload()

    def load_activity_btn(self):
        cmd = {
            'user_id': self.user_id.id,
            'activity_type_id': self.activity_type_id.id,
            'summary': self.summary,
            'date_deadline': self.date_deadline,
            'activity_source': self.activity_source,
            'category_id': self.category_id.id,
            'product_id': self.product_id.id,
            'department_id': self.department_id.id,
            'workcenter_id': self.workcenter_id.id,
            'workcenter_ids': [(6, False, self.workcenter_ids.ids)],
            'analytic_id': self.analytic_id.id}
        self.activity_ids = [(0, 0, cmd)]
        return self.reload()

    def create_activity_btn(self):
        for res_id in self.res_ids.filtered(lambda r: r.to_clone is False):
            record = self.env[res_id.res_model].browse([res_id.res_id]) if res_id.res_name != 'NotFound' else None
            if record:
                record.activity_ids = [(0, 0, {'activity_source': activity_id.activity_source,
                                               'category_id': activity_id.category_id.id,
                                               'product_id': activity_id.product_id.id,
                                               'department_id': activity_id.department_id.id,
                                               'date_deadline': str(activity_id.date_deadline),
                                               'res_model': res_id.res_model,
                                               'res_model_id': res_id.res_model_id.id,
                                               'res_id': res_id.res_id,
                                               'res_name': res_id.res_name,
                                               'summary': activity_id.summary,
                                               'note': activity_id.note,
                                               'tracking_state': activity_id.tracking_state,
                                               'manual_analytic_id': activity_id.analytic_id.id if activity_id.analytic_id else res_id.analytic_id.id,
                                               'workcenter_ids': [(6, 0, activity_id.workcenter_ids.ids)]})
                                        for activity_id in self.activity_ids]
                for activity_id in self.activity_ids.filtered(lambda r: r.send_to_tracking is True):
                    record.activity_ids.filtered(lambda r: r.res_id == activity_id.res_id and
                                                 r.res_model_id.id == activity_id.res_model_id.id and
                                                 r.product_id.id == activity_id.product_id.id and
                                                 r.date_deadline == activity_id.date_deadline and
                                                 r.activity_source == activity_id.activity_source).create_tracking_btn()


class MailActivityConfiguratorRes(models.TransientModel):
    _name = 'mail.activity.configurator.res'
    _description = 'mail.activity.configurator.res'

    configurator_id = fields.Many2one('mail.activity.configurator')
    res_id = fields.Integer(required=True, string='ID')
    res_name = fields.Char(compute='_compute_res_name')
    res_model_id = fields.Many2one('ir.model', required=True, ondelete='cascade')
    res_model = fields.Char(related='res_model_id.model')
    analytic_id = fields.Many2one('account.analytic.account', compute='_compute_analytic_id',
                                  string='Analytic')
    to_clone = fields.Boolean(default=False)

    @api.depends('res_model', 'res_id')
    def _compute_res_name(self):
        for r in self:
            r.res_name = self.env[r.res_model].browse([r.res_id]).name if r.res_model and r.res_id else 'NotFound'

    @api.depends('res_model_id', 'res_model', 'res_id')
    def _compute_analytic_id(self):
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
            r.analytic_id = analytic_id

    def load_activity_btn(self):
        self.configurator_id.to_clone = False
        self.to_clone = True
        record = self.env[self.res_model].browse([self.res_id]) if self.res_name != 'NotFound' else None
        if record:
            self.configurator_id.activity_ids = [(0, 0, {'activity_source': activity_id.activity_source,
                                                   'category_id': activity_id.category_id.id,
                                                   'product_id': activity_id.product_id.id,
                                                   'department_id': activity_id.department_id.id,
                                                   'date_deadline': str(activity_id.date_deadline),
                                                   'summary': activity_id.summary,
                                                   'analytic_id': activity_id.analytic_id.id,
                                                   'workcenter_ids': [(6, 0, activity_id.workcenter_ids.ids)]})
                                         for activity_id in record.activity_ids]
        return self.configurator_id.reload()


class MailActivityConfiguratorActivity(models.TransientModel):
    _name = 'mail.activity.configurator.activity'
    _description = 'mail.activity.configurator.activity'

    configurator_id = fields.Many2one('mail.activity.configurator')
    user_id = fields.Many2one(
        'res.users', 'Assigned to',
        default=lambda self: self.env.user,
        index=True, required=True, ondelete='cascade')
    activity_type_id = fields.Many2one('mail.activity.type', string='Activity Type')
    summary = fields.Char('Summary')
    date_deadline = fields.Date('Due Date', index=True, required=True, default=fields.Date.context_today)
    activity_source = fields.Selection([('normal', 'Normal'),
                                        ('restriction', 'Restriction'),
                                        ('noncompliance', 'Noncompliance'),
                                        ('nonconformity', 'Nonconformity')], default='restriction')
    category_id = fields.Many2one('product.category', 'Category')
    product_id = fields.Many2one('product.product')
    department_id = fields.Many2one('hr.department', string="Department")
    workcenter_id = fields.Many2one('mrp.workcenter')
    workcenter_ids = fields.Many2many('mrp.workcenter', 'mrp_activity_workcenter_conf_act_rel', 'activity_id',
                                      'workcenter_id')
    analytic_id = fields.Many2one('account.analytic.account', string='Analytic Account')
    note = fields.Html('Note')
    tracking_state = fields.Selection([('unlocked', 'Unlocked'), ('locked', 'Locked')], default='locked', string='State')
    send_to_tracking = fields.Boolean(default=False)

    @api.onchange('activity_source')
    def onchange_activity_source(self):
        valid = True
        if self.activity_source == 'restriction':
            field_name = 'is_restriction'
        elif self.activity_source == 'noncompliance':
            field_name = 'is_noncompliance'
        elif self.activity_source == 'nonconformity':
            field_name = 'is_nonconformity'
        else:
            valid = False
        if valid:
            categ_ids = self.env['product.product'].search([(field_name, '=', True)]).mapped('categ_id').ids
            if self.category_id.id not in categ_ids:
                self.category_id = None
                self.product_id = None
            return {
                'domain': {
                    'category_id': [('id', 'in', categ_ids)],
                }
            }
        else:
            self.category_id = None
            self.product_id = None

    @api.onchange('category_id')
    def onchange_category_id(self):
        if self.product_id.categ_id != self.category_id.id:
            self.product_id = None
        search_args = [('bom_type', 'in', ('basic', 'workorder')), ('categ_id', '=', self.category_id.id)]
        if self.activity_source == 'restriction':
            search_args.append(('is_restriction', '=', True))
        elif self.activity_source == 'noncompliance':
            search_args.append(('is_noncompliance', '=', True))
        elif self.activity_source == 'nonconformity':
            search_args.append(('is_nonconformity', '=', True))
        product_ids = self.env['product.product'].search(search_args).ids
        return {
            'domain': {
                'product_id': [('id', 'in', product_ids)],
            }
        }


# -*- coding: utf-8 -*-

from odoo import api, exceptions, fields, models, modules, _, SUPERUSER_ID
from odoo.http import request


class ResUsers(models.Model):

    _inherit = 'res.users'

    activity_by = fields.Selection([('user', 'User'), ('workcenter', 'Workcenter')], default='user')
    shared_account = fields.Boolean('Shared Account', default=False)
    block_creation = fields.Selection([('current', 'Only current day'),
                                       ('period', 'period restrictions'),
                                       ('open', 'Anytime')], default='current', required=True)

    @api.model
    def systray_get_activities(self):
        """ If user have not scheduled any note, it will not appear in activity menu.
            Making note activity always visible with number of notes on label. If there is no notes,
            activity menu not visible for note.
        """
        activities = super(ResUsers, self).systray_get_activities()
        if self.env.user.activity_by == 'workcenter':
            # Keep Notes
            activities = [activity for activity in activities if activity['model'] == 'note.note']
            # Get Workcenters related by Contract
            if request.session.get('session_workcenter'):
                workcenter_id = self.env['mrp.workcenter'].browse([request.session.get('session_workcenter')])
                workcenter_ids = tuple(workcenter_id.contract_id.workcenter_ids.ids)
            else:
                employee_id = self.env['hr.employee'].search([('user_id', '=', self.env.user.id)], limit=1).id
                contract_id = self.env['hr.contract'].search([('employee_id', '=', employee_id),
                                                              ('state', 'in', ['open', 'pending'])], limit=1)
                workcenter_ids = tuple(contract_id.workcenter_id.ids)
            # Just if we have workcenter info
            if workcenter_ids:
                query = """SELECT m.id, count(*), act.res_model as model,
                                        CASE
                                            WHEN %(today)s::date - act.date_deadline::date = 0 Then 'today'
                                            WHEN %(today)s::date - act.date_deadline::date > 0 Then 'overdue'
                                            WHEN %(today)s::date - act.date_deadline::date < 0 Then 'planned'
                                        END AS states
                                    FROM mail_activity AS act
                                    JOIN ir_model AS m ON act.res_model_id = m.id
                                    JOIN mrp_activity_workcenter_rel as aw ON act.id = aw.activity_id
                                    WHERE aw.workcenter_id in %(workcenter_ids)s
                                    GROUP BY m.id, states, act.res_model;
                                    """
                self.env.cr.execute(query, {
                    'today': fields.Date.context_today(self),
                    'workcenter_ids': workcenter_ids,
                })
                activity_data = self.env.cr.dictfetchall()
                model_ids = [a['id'] for a in activity_data]
                model_names = {n[0]: n[1] for n in self.env['ir.model'].browse(model_ids).name_get()}

                user_activities = {}
                for activity in activity_data:
                    if not user_activities.get(activity['model']):
                        module = self.env[activity['model']]._original_module
                        icon = module and modules.module.get_module_icon(module)
                        user_activities[activity['model']] = {
                            'name': model_names[activity['id']],
                            'model': activity['model'],
                            'type': 'activity',
                            'icon': icon,
                            'total_count': 0, 'today_count': 0, 'overdue_count': 0, 'planned_count': 0,
                        }
                    user_activities[activity['model']]['%s_count' % activity['states']] += activity['count']
                    if activity['states'] in ('today', 'overdue'):
                        user_activities[activity['model']]['total_count'] += activity['count']

                    user_activities[activity['model']]['actions'] = [{
                        'icon': 'fa-clock-o',
                        'name': 'Summary',
                    }]
                for activity in list(user_activities.values()):
                    activities.append(activity)
        return activities
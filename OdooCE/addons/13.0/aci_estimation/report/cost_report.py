# -*- coding: utf-8 -*-

from datetime import datetime, timedelta

from odoo import models, fields, api


class CostReportView(models.AbstractModel):
    """
        Abstract Model specially for report template.
        _name = Use prefix `report.` along with `module_name.report_name`
    """
    _name = 'report.aci_estimation.cost_estim_period_report_view'
    _description = 'report.aci_estimation.cost_estim_period_report_view'

    @api.model
    def _get_report_values(self, docids, data=None):
        period_start_id = data['form']['period_start_id']
        period_end_id = data['form']['period_end_id']

        Period = self.env['payment.period']
        Productivity = self.env['mrp.workcenter.productivity']

        period_id = Period.browse([period_start_id])
        period_start_id = Period.browse([period_start_id])
        period_end_id = Period.browse([period_end_id])

        report_total_pay = 0
        report_total_extra = 0
        report_total_discount = 0
        report_total_deposit = 0
        report_total_cost = 0

        docs = []
        while period_start_id.global_sequence <= period_end_id.global_sequence:
            productivity_ids = Productivity.search([
                ('qty_status', '=', 'approved'),
                ('final_start_date', '>=', period_start_id.from_date),
                ('final_start_date', '<=',  period_start_id.to_date)
            ], order='party_id ASC, workorder_by_step ASC, analytic_name ASC')
            for workcenter_id in productivity_ids.mapped('resource_id'):
                wk_ids = productivity_ids.filtered(lambda r: r.resource_id.id == workcenter_id.id)
                for workorder_id in wk_ids.mapped('workorder_by_step'):
                    wk_productivitiy_ids = productivity_ids.filtered(lambda r: r.resource_id.id == workcenter_id.id and
                                                                        r.workorder_by_step.id == workorder_id.id)
                    qty = round(sum(wk_productivitiy_ids.mapped('wo_qty_progress')), 2)
                    duration = round(sum(wk_productivitiy_ids.mapped('duration')), 2)
                    worked_duration = round(sum(wk_productivitiy_ids.mapped('worked_duration')), 2)
                    total_pay = round(sum(wk_productivitiy_ids.mapped('total_pay_amount')), 2)
                    total_extra = round(sum(wk_productivitiy_ids.mapped('total_operation_extra')), 2)
                    total_discount = round(sum(wk_productivitiy_ids.mapped('discount')), 2)
                    total_deposit = round(sum(wk_productivitiy_ids.mapped('deposit')), 2)
                    total_cost = round(sum(wk_productivitiy_ids.mapped('total_cost')), 2)
                    crew = round(sum(wk_productivitiy_ids.mapped('qty_operators')) / len(wk_productivitiy_ids.mapped('qty_operators')), 2)
                    docs.append({
                        'type': 'row',
                        'period': period_start_id.name,
                        'workcenter': workcenter_id.name,
                        'employee': workcenter_id.employee_id.name,
                        'party': workorder_id.party_id.complete_name,
                        'concept': workorder_id.product_wo.name,
                        'location': workorder_id.analytic_id.name,
                        'qty': '{:,.2f}'.format(qty),
                        'duration': '{:,.2f}'.format(duration),
                        'crew': '{:,.2f}'.format(crew),
                        'worked_duration': '{:,.2f}'.format(worked_duration),
                        'total_pay': '${:,.2f}'.format(total_pay),
                        'total_extra': '${:,.2f}'.format(total_extra),
                        'total_discount': '-${:,.2f}'.format(total_discount),
                        'total_deposit': '-${:,.2f}'.format(total_deposit),
                        'total_cost': '${:,.2f}'.format(total_cost)
                    })

                total_pay = round(sum(wk_ids.mapped('total_pay_amount')), 2)
                total_extra = round(sum(wk_ids.mapped('total_operation_extra')), 2)
                total_discount = round(sum(wk_ids.mapped('discount')), 2)
                total_deposit = round(sum(wk_ids.mapped('deposit')), 2)
                total_cost = round(sum(wk_ids.mapped('total_cost')), 2)

                report_total_pay = report_total_pay + total_pay
                report_total_extra = report_total_extra + total_extra
                report_total_discount = report_total_discount + total_discount
                report_total_deposit = report_total_deposit + total_deposit
                report_total_cost = report_total_cost + total_cost

                docs.append({
                    'type': 'total',
                    'period': '',
                    'workcenter': '',
                    'employee': '',
                    'party': '',
                    'concept': '',
                    'location': '',
                    'qty': '',
                    'duration': '',
                    'crew': '',
                    'worked_duration': 'Total=',
                    'total_pay': '${:,.2f}'.format(total_pay),
                    'total_extra': '${:,.2f}'.format(total_extra),
                    'total_discount': '-${:,.2f}'.format(total_discount),
                    'total_deposit': '-${:,.2f}'.format(total_deposit),
                    'total_cost': '${:,.2f}'.format(total_cost)
                })
                docs.append({
                    'type': 'empty',
                    'period': '',
                    'workcenter': '',
                    'employee': '',
                    'party': '',
                    'concept': '',
                    'location': '',
                    'qty': '',
                    'duration': '',
                    'crew': '',
                    'worked_duration': '',
                    'total_pay': '',
                    'total_extra': '',
                    'total_discount': '',
                    'total_deposit': '',
                    'total_cost': ''
                })

            period_start_id = Period.search([('group_id', '=', period_start_id.group_id.id),
                                             ('global_sequence', '=', period_start_id.global_sequence + 1)])

        docs.append({
            'type': 'total',
            'period': '',
            'workcenter': '',
            'employee': '',
            'party': '',
            'concept': '',
            'location': '',
            'qty': '',
            'duration': '',
            'crew': '',
            'worked_duration': 'TOTAL=',
            'total_pay': '${:,.2f}'.format(report_total_pay),
            'total_extra': '${:,.2f}'.format(report_total_extra),
            'total_discount': '${:,.2f}'.format(report_total_discount),
            'total_deposit': '${:,.2f}'.format(report_total_deposit),
            'total_cost': '${:,.2f}'.format(report_total_cost)
        })
        return {
            'doc_ids': data['ids'],
            'doc_model': data['model'],
            'period_id': period_id,
            'docs': docs,
        }
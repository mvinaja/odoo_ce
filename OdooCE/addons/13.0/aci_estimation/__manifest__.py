{
    'name': 'ACI Estimation',

    'summary': '''
        ToDo
    ''',

    'description': '''
        ToDo  
    ''',

    'author': 'Alce Consorcio Inmobiliario SA de CV',
    'website': 'http://www.casasalce.com',

    'category': 'Project, Usability, Specific Industry Applications',
    'version': '1.0',

    'depends': [
        'base', 'web',
        'hr', 'hr_contract',
        'hr_attendance', 'sale_timesheet', 'hr_payroll', 'project_timesheet_holidays',
        'aci_mrp', 'aci_lbm_flowline', 'web_timeline'
    ],

    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',

        'data/web_assets.xml',
        'data/restrictions.xml',
        'data/stages.xml',
        'data/periodicity.xml',
        'data/cron.xml',
        'data/paper_format.xml',

        'views/quality_alert.xml',
        'views/stock_warehouse_views.xml',
        'views/product_views.xml',
        'views/mail_activity_views.xml',
        'views/res_config_views.xml',
        'views/res_users_views.xml',
        'views/resource_calendar_views.xml',
        'views/payment_period_views.xml',
        'views/mrp_views.xml',
        'views/lbm_work_order_step_views.xml',
        'views/mrp_workcenter_productivity_views.xml',
        'views/hr_contract_views.xml',
        'views/hr_attendance_views.xml',
        'views/attendance_log_views.xml',
        'views/attendance_incidence_views.xml',
        'views/hr_productivity_block_views.xml',
        'views/hr_employee_views.xml',
        'views/zk_machine_view.xml',
        'views/res_users_views.xml',
        'views/mrp_estimation_views.xml',
        'views/mrp_timetracking_views.xml',
        'views/lbm_baseline_views.xml',
        'views/lbm_workorder_views.xml',
        'views/lbm_baseline_report_views.xml',
        'views/hr_department_views.xml',
        'views/lbm_period_views.xml',
        'views/lbm_period_workcenter_views.xml',
        'views/mrp_routing_views.xml',

        # 'views/mrp_estimation_report_views.xml',

        'wizard/hr_attendance_actions_views.xml',
        'wizard/attendance_log_actions_views.xml',
        'wizard/attendance_incidence_actions_views.xml',
        'wizard/hr_contract_actions_views.xml',
        'wizard/hr_productivity_block_incidence_views.xml',
        'wizard/hr_productivity_block_timeoff_views.xml',
        'wizard/hr_zk_biometric_block_wizard_views.xml',
        'wizard/hr_zk_biometric_log_wizard_views.xml',
        'wizard/hr_employee_actions_views.xml',
        'wizard/mrp_estimation_wizard_views.xml',
        'wizard/mrp_production_actions_views.xml',
        'wizard/mrp_timetracking_activity_views.xml',
        'wizard/mrp_tracking_access_views.xml',
        'wizard/mrp_timetracking_wizard_views.xml',
        'wizard/time_tracking_views.xml',
        'wizard/mrp_workcenter_actions.xml',
        'wizard/popup_message.xml',
        'wizard/mrp_estimation_calculator_views.xml',
        'wizard/mail_activity_configurator.xml',
        'wizard/update_operation_data_views.xml',
        'wizard/add_workstep_views.xml',
        'wizard/compare_bom_wizard_views.xml',

        'report/cost_report.xml'
    ],
    'demo': [
    ],
    'css': ['static/src/css/time_tracking_css.css',
            'static/src/css/kanban_stages.css'],
    'qweb': [
        # 'static/src/xml/activity.xml',
        'static/src/xml/filter.xml',
        'static/src/xml/accum_time.xml',
        'static/src/xml/timetracking.backend.xml',
        'static/src/xml/base.xml'],
    'application': True,
}
# -*- coding: utf-8 -*-

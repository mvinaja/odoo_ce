# -*- coding: utf-8 -*-
{
    'name': "aci_product",

    'summary': """
    Lean Construction Product Properties
    """,

    'description': """
    Alce Consorcio's Product
    """,

    'author': "Alce Consorcio Inmobiliario SA de CV",
    'website': "http://www.casasalce.com",

    'category': 'Inventory, Specific Industry Applications, Manufacturing',
    'version': '1.0',

    'depends': [
        'base',
        'hr',
        'hr_contract',
        'mrp',
        'mrp_plm',
        'mrp_mps',
        'quality_mrp',
        'product',
        'purchase',
        'stock',
        'account_accountant',
        'account_budget',
        'l10n_mx',
        'website_sale_stock',
        'website_sale_comparison',
        'sale_timesheet',
        'aci_context',
        'aci_gantt',
        'aci_tree_buttons'
    ],

    'data': [
        'data/configuration.xml',
        'data/budgetary_position.xml',
        # 'data/demo_data.xml',

        'security/ir.model.access.csv',
        'security/mrp_groups.xml',

        'views/product_category_views.xml',
        'views/product_attribute_views.xml',
        'views/product_views.xml',
        'views/mrp_workcenter_views.xml',
        'views/stock_warehouse_views.xml',

        'wizards/create_attribute_value_views.xml',
        'wizards/create_product_views.xml',
        'wizards/create_template_views.xml',
        'wizards/update_sequence_views.xml',
        'wizards/update_product_attribute_views.xml',
        'wizards/update_attribute_state_views.xml',
        'wizards/add_workcenter_member_views.xml',
        'views/aci_product_menus.xml',
    ],

    'qweb': [
        'static/src/xml/*.xml'
    ],

    'demo': [
    ],
}

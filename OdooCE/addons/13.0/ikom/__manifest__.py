###################################################################################
#
#    Copyright (c) 2021 Marco Vinaja
##
###################################################################################
{
    "name": "IKOM Sales",
    "summary": "IKOM sales project by Marco Vinaja",
    "version": "13",
    'category': 'Sales, Specific Industry Applications',
    "author": "Marco Vinaja",
    "depends": [
          "stock", "muk_web_theme", "sale_management"
    ],
    "excludes": [
        "web_enterprise",
    ],
    "data": [
        'security/ir.model.access.csv',

        'data/settings.xml',
        'data/demo.xml',

        'views/product_template_views.xml',
        'views/sales_order_views.xml',
        'views/sale_order_line_views.xml',

        'wizards/package_wizard.xml',
    ],
    "qweb": [
    ],
    "application": False,
    "installable": True,
    "auto_install": False,
}
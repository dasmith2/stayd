"""
pip install selenium
"""

from bgcheck.management.commands.us_id_cc_test import USIDCCTest
from bgcheck.management.commands.opt_out_web_test import OptOutWebTest
from nps.management.commands.nps_test import NPSTest
from util.web_test import WebTestCommand
from va.management.commands.id_verify_test import IDVerifyWebTest
from va.management.commands.approve_high_risk_test import HighRiskWebTest
from work.management.commands.clean_co_test import CleanCoTest
from work.management.commands.maintenance_test import MaintenanceWebTest
from work.management.commands.review_cleaning_test import ReviewCleaningTest


class Command(WebTestCommand):
  help = 'Run all the web tests.'

  def web_test_classes(self):
    return [
        IDVerifyWebTest, HighRiskWebTest, OptOutWebTest, USIDCCTest,
        MaintenanceWebTest, CleanCoTest, ReviewCleaningTest, NPSTest]

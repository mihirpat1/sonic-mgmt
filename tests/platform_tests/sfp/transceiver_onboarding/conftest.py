import csv
import os
import pytest
import logging

from tests.common.platform.interface_utils import get_physical_port_indices


class TransceiverInventory:
    def __init__(self, base_path):
        self.base_path = base_path
        self.transceiver_inventory_path = os.path.join(
            self.base_path, "../../../../ansible/files/transceiver_inventory/"
        )
        self.common_attributes_file = os.path.join(self.transceiver_inventory_path, "transceiver_common_attributes.csv")
        self.dut_info_file = os.path.join(self.transceiver_inventory_path, "transceiver_dut_info.csv")
        self.common_attributes = self.parse_common_attributes()
        self.dut_info = self.parse_dut_info()

    def parse_common_attributes(self):
        """
        Parses the transceiver_common_attributes.csv file and stores the data in a dictionary.
        The vendor_pn is used as the key for the outer dictionary, and the remaining row data is stored as the value.
        """
        common_attributes = {}
        with open(self.common_attributes_file, mode='r') as file:
            reader = csv.DictReader(file)
            for row in reader:
                vendor_pn = row['vendor_pn']
                common_attributes[vendor_pn] = self.convert_row_types(row)
        logging.debug("Common Attributes: {}".format(common_attributes))
        return common_attributes

    def parse_dut_info(self):
        """
        Parses the transceiver_dut_info.csv file and stores the data in a nested dictionary.
        The outer dictionary is keyed by dut_name, and the inner dictionary is keyed by physical_port.
        The values are dictionaries containing the remaining row data.
        Common attributes are merged into the inner dictionary based on vendor_pn.
        """
        dut_info = {}
        with open(self.dut_info_file, mode='r') as file:
            reader = csv.DictReader(file)
            for row in reader:
                dut_name = row.pop('dut_name')
                port = int(row.pop('physical_port'))
                vendor_pn = row.pop('vendor_pn')
                if dut_name not in dut_info:
                    dut_info[dut_name] = {}
                dut_info[dut_name][port] = self.convert_row_types(row)
                if vendor_pn in self.common_attributes:
                    dut_info[dut_name][port].update(self.common_attributes[vendor_pn])
        logging.debug("DUT Info: {}".format(dut_info))
        return dut_info

    def convert_row_types(self, row):
        """
        Converts the values in a row to their appropriate types (e.g., int, float, bool).
        This is required since default csv.DictReader returns all values as strings, we need to
        convert them to their appropriate types.
        """
        special_handling = {
            'dual_bank_support': lambda x: x == 'True',
        }
        return {key: special_handling.get(key, lambda x: x)(value) for key, value in row.items()}

    def get_transceiver_info(self):
        """
        Returns the parsed transceiver information.
        """
        return self.dut_info


@pytest.fixture(scope="module")
def transceiver_inventory():
    """
    Fixture to provide transceiver inventory information.
    """
    base_path = os.path.dirname(os.path.realpath(__file__))
    inventory = TransceiverInventory(base_path)
    return inventory.get_transceiver_info()


@pytest.fixture(scope="module")
def get_lport_to_pport_mapping(duthosts, enum_rand_one_per_hwsku_frontend_hostname, tbinfo):
    """
    Fixture to get the mapping of logical ports to physical ports.
    """
    duthost = duthosts[enum_rand_one_per_hwsku_frontend_hostname]
    lport_to_pport_mapping = get_physical_port_indices(duthost)
    logging.info("Logical to Physical Port Mapping: {}".format(lport_to_pport_mapping))
    return lport_to_pport_mapping

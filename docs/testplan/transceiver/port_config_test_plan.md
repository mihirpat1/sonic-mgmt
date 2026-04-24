# Port Configuration Test Plan For Transceivers

## Overview

The Port Configuration Test Plan outlines the testing strategy for validating that per-port configuration in CONFIG_DB (speed, FEC, etc) is consistent with the expected values defined in the transceiver inventory. These tests verify the switch's port configuration layer rather than transceiver EEPROM registers, and are topology-independent.

## Scope

The scope of this test plan includes the following:

- Validation of per-port speed configuration in CONFIG_DB against expected `speed_gbps` from `BASE_ATTRIBUTES`
- Validation of FEC mode configuration in CONFIG_DB for high-speed ports (≥ 200 Gbps)
- Validation of MTU configuration in CONFIG_DB against expected `expected_mtu` from `PORT_CONFIG_ATTRIBUTES`
- Validation of auto-negotiation setting in CONFIG_DB against expected `expected_autoneg` from `PORT_CONFIG_ATTRIBUTES`
- Validation that all transceiver ports are administratively up in CONFIG_DB
- Cross-layer consistency: speed alignment between CONFIG_DB PORT table and STATE_DB PORT_TABLE
- Cross-layer consistency: FEC alignment between CONFIG_DB PORT table and STATE_DB PORT_TABLE
- Cross-layer consistency: autoneg alignment between CONFIG_DB PORT table and APPL_DB PORT_TABLE

## Optics Scope

All the optics covered in the parent [Transceiver Onboarding Test Infrastructure and Framework](test_plan.md#scope)

## Testbed Topology

Please refer to the [Testbed Topology](test_plan.md#testbed-topology)

## Pre-requisites

Before executing the port configuration tests, ensure the following pre-requisites are met:

### Setup Requirements

- The testbed is set up according to the [Testbed Topology](test_plan.md#testbed-topology)
- All the pre-requisites mentioned in [Transceiver Onboarding Test Infrastructure and Framework](test_plan.md#test-prerequisites-and-configuration-files) must be met

### Environment Validation

Before starting tests, verify the following system conditions:

1. **System Health Check**
   - All critical services are running (xcvrd, pmon, swss, syncd) for at least 5 minutes
   - No existing system errors in logs

2. **Configuration Validation**
   - `dut_info/<dut_hostname>.json` is present and contains `speed_gbps` and `host_lane_mask` in `BASE_ATTRIBUTES` for all ports under test
   - `port_config.json` is properly formatted and accessible if MTU or autoneg validation is desired; when absent, those test cases skip gracefully
   - All required attributes are defined for the ports under test

## Attributes

Port configuration tests draw from two attribute sources:

- **BASE_ATTRIBUTES** (from `dut_info/<dut_hostname>.json`): Provides `speed_gbps` and `host_lane_mask`, used by port admin/status, speed, FEC, DOM polling, and cross-layer speed/FEC consistency tests. These attributes are always present because `dut_info` is a mandatory input file.
- **PORT_CONFIG_ATTRIBUTES** (from `port_config.json`): Provides `expected_mtu` and `expected_autoneg`, used by MTU validation, autoneg validation, and cross-layer autoneg consistency tests. When `port_config.json` is absent or an attribute is not defined for a port, the corresponding test cases skip that port gracefully.

The following table summarizes the key attributes used in port configuration testing. This table serves as the authoritative reference for all attributes and must be updated whenever new attributes are introduced:

**Legend:** M = Mandatory, O = Optional

| Attribute Name | Source | Type | Default Value | Mandatory | Override Levels | Description |
|----------------|--------|------|---------------|-----------|-----------------|-------------|
| expected_mtu | PORT_CONFIG_ATTRIBUTES | integer | - | O | transceivers or platform | Expected MTU for the port in CONFIG_DB. When absent, the MTU validation test is skipped for that port. |
| expected_autoneg | PORT_CONFIG_ATTRIBUTES | string | off | O | transceivers or platform | Expected auto-negotiation setting (`"on"` or `"off"`). When absent, the autoneg validation tests are skipped for that port. DAC cables typically require `"off"`; value should align with `cable_type` in `BASE_ATTRIBUTES`. |

For information about attribute override hierarchy and precedence, please refer to the [Priority-Based Attribute Resolution](test_plan.md#priority-based-attribute-resolution) documentation.

## CLI Commands Reference

For detailed CLI commands used in the test cases below, please refer to the [CLI Commands section](test_plan.md#cli-commands) in the Transceiver Onboarding Test Infrastructure and Framework. This section provides comprehensive examples of all relevant commands.

The primary database queries used in these tests are:

```bash
# CONFIG_DB — configured port parameter
sonic-db-cli CONFIG_DB hgetall 'PORT|<port_name>'

# CONFIG_DB — DOM polling status for a specific port
sonic-db-cli CONFIG_DB hget 'PORT|<port_name>' dom_polling

# APPL_DB — port parameters as applied by orchagent
#   Fields sourced from here: oper_status, admin_status, mtu, fec (admin), autoneg, lanes
sonic-db-cli APPL_DB hgetall 'PORT_TABLE:<port_name>'

# APPL_DB — link operational status for a specific port
sonic-db-cli APPL_DB hget 'PORT_TABLE:<port_name>' oper_status

# STATE_DB
#   Fields sourced from here: speed (oper), fec (oper)
sonic-db-cli STATE_DB hgetall 'PORT_TABLE|<port_name>'
```

## Test Cases

**Assumptions for the Below Tests:**

- All the below tests will be executed for all the transceivers connected to the DUT (the port list is derived from the `port_attributes_dict`) unless specified otherwise.

### Common Test Setup and Teardown

The following setup and teardown steps apply to **all test cases** in this plan unless a subcategory explicitly overrides them.

#### Session-Level Setup (once per test run)

1. **Service health**: Verify all critical services (xcvrd, pmon, swss, syncd) are running. All tests in this plan are read-only DB queries and do not affect service health; re-checking per test would be unnecessary overhead.

#### Per-Test Setup (before each test case)

1. **Log baseline**: Record the current position in system logs so post-test inspection can isolate entries introduced by the test.

#### Common Teardown (after each test case)

1. **Log inspection**: Scan system logs from the baseline position for unexpected errors. All tests in this plan are read-only DB queries and should not introduce any errors.

### Port Configuration and Status Validation

**Subcategory setup/teardown**: No additional setup or teardown beyond [Common Test Setup and Teardown](#common-test-setup-and-teardown). All tests in this subcategory are read-only CONFIG_DB and APPL_DB queries and do not modify any system state.

| TC No. | Test | Steps | Expected Results |
|--------|------|-------|------------------|
| 1 | Port admin status validation in CONFIG_DB | 1. For each port in `port_attributes_dict`, query `sonic-db-cli CONFIG_DB hgetall 'PORT\|<port>'` to retrieve the configured `admin_status`.<br>2. Assert that `admin_status` equals `"up"` for every port.<br>3. Aggregate all failures and report at the end. | All ports in `port_attributes_dict` have `admin_status` set to `"up"` in CONFIG_DB. Any port found admin-down is a misconfiguration that must be identified and logged |
| 2 | Link operational status validation in APPL_DB | 1. For each port in `port_attributes_dict`, query `sonic-db-cli APPL_DB hget 'PORT_TABLE:<port>' oper_status` to retrieve the operational link status.<br>2. Assert that `oper_status` equals `"up"` for every port.<br>3. Aggregate all failures and report at the end. | All ports in `port_attributes_dict` have `oper_status` set to `"up"` in APPL_DB PORT_TABLE. Any port that is operationally down despite being admin-up and having a transceiver present indicates a cable, transceiver, or configuration issue that must be identified and logged. |
| 3 | Port speed validation in CONFIG_DB | 1. Retrieve the `speed_gbps` attribute from BASE_ATTRIBUTES in `port_attributes_dict` for the port.<br>2. Query the PORT table in CONFIG_DB to retrieve the configured speed for the port.<br>3. Convert the CONFIG_DB speed value to Gbps (e.g., "100000" → 100 Gbps, "400000" → 400 Gbps).<br>4. Compare the converted speed value with the `speed_gbps` attribute.<br>5. Aggregate all mismatches and report at the end. | 1. CONFIG_DB PORT table contains a `speed` field for the port.<br>2. Speed value from CONFIG_DB matches the `speed_gbps` attribute from BASE_ATTRIBUTES.<br>3. Any mismatches between configured and expected speed are identified and logged. |
| 4 | FEC configuration validation in CONFIG_DB | 1. Retrieve the `speed_gbps` attribute from BASE_ATTRIBUTES in `port_attributes_dict` for the port.<br>2. If `speed_gbps` is < 200 Gbps, skip the port.<br>3. Query the PORT table in CONFIG_DB to retrieve the configured FEC mode for the port.<br>4. Verify that FEC is set to `rs` for ports ≥ 200 Gbps.<br>5. Aggregate all mismatches and report at the end. | 1. CONFIG_DB PORT table contains a `fec` field for all ports ≥ 200 Gbps.<br>2. FEC is configured as `rs` for all ports ≥ 200 Gbps.<br>3. Any mismatches are identified and logged. |
| 5 | MTU configuration validation in CONFIG_DB | 1. Retrieve the `expected_mtu` attribute from PORT_CONFIG_ATTRIBUTES in `port_attributes_dict` for the port.<br>2. If `expected_mtu` is absent, skip the port.<br>3. Query `sonic-db-cli CONFIG_DB hgetall 'PORT\|<port>'` to retrieve the configured MTU.<br>4. Compare the actual MTU against `expected_mtu`.<br>5. Aggregate all mismatches and report at the end. | 1. CONFIG_DB PORT table contains an `mtu` field for the port.<br>2. MTU value matches `expected_mtu` from PORT_CONFIG_ATTRIBUTES.<br>3. Any misconfigured MTU values are identified and logged. |
| 6 | Auto-negotiation setting validation in CONFIG_DB | 1. Retrieve the `expected_autoneg` attribute from PORT_CONFIG_ATTRIBUTES in `port_attributes_dict` for the port.<br>2. If `expected_autoneg` is absent, skip the port.<br>3. Query `sonic-db-cli CONFIG_DB hgetall 'PORT\|<port>'` to retrieve the configured `autoneg` setting.<br>4. Compare the actual value against `expected_autoneg` (`"on"` or `"off"`).<br>5. Aggregate all mismatches and report at the end. | 1. CONFIG_DB PORT table contains an `autoneg` field for the port.<br>2. Auto-negotiation setting matches `expected_autoneg` from PORT_CONFIG_ATTRIBUTES.<br>3. Any mismatches (e.g., DAC cables with autoneg incorrectly enabled) are identified and logged. |
| 7 | DOM polling enabled validation in CONFIG_DB | 1. For each port in `port_attributes_dict`, determine whether it is the first subport of its breakout group (i.e., `host_lane_mask` in BASE_ATTRIBUTES indicates it owns the first host lane). Skip the port if it is not the first subport of a breakout group.<br>2. Query `sonic-db-cli CONFIG_DB hget 'PORT\|<port>' dom_polling` to retrieve the DOM polling setting.<br>3. If the field is absent, treat DOM polling as enabled (per SONiC default behaviour) and pass.<br>4. If the field is present and equals `"enabled"`, pass.<br>5. If the field is present and equals `"disabled"`, record a failure.<br>6. Aggregate all failures and report at the end. | 1. For all first subports of breakout groups (and non-breakout ports), the `dom_polling` field in CONFIG_DB PORT table is either absent or set to `"enabled"`.<br>2. Any port with `dom_polling` explicitly set to `"disabled"` is identified and logged as a misconfiguration — DOM data will not be populated in STATE_DB for that port, causing DOM tests to fail. |

### Cross-Layer Consistency

**Subcategory setup/teardown**: No additional setup or teardown beyond [Common Test Setup and Teardown](#common-test-setup-and-teardown). All tests in this subcategory are read-only multi-DB comparison queries and do not modify any system state.

| TC No. | Test | Steps | Expected Results |
|--------|------|-------|------------------|
| 8 | Speed consistency: CONFIG_DB vs STATE_DB (platform oper speed) | 1. For each port, query `sonic-db-cli CONFIG_DB hgetall 'PORT\|<port>'` to retrieve the configured speed.<br>2. Query `sonic-db-cli STATE_DB hgetall 'PORT_TABLE\|<port>'` to retrieve the operational speed as reported by the platform driver.<br>3. Convert both values to Gbps and compare.<br>4. Aggregate all mismatches and report at the end. | 1. STATE_DB PORT_TABLE contains a `speed` field for the port.<br>2. Operational speed in STATE_DB matches the configured speed in CONFIG_DB.<br>3. Any mismatches (port came up at a different speed than configured) are identified and logged. |
| 9 | FEC consistency: CONFIG_DB vs STATE_DB (platform oper FEC) | 1. For each port with speed ≥ 200 Gbps, query `sonic-db-cli CONFIG_DB hgetall 'PORT\|<port>'` to retrieve the configured FEC mode.<br>2. Query `sonic-db-cli STATE_DB hgetall 'PORT_TABLE\|<port>'` to retrieve the operational FEC mode as reported by the platform driver.<br>3. Compare both values.<br>4. Aggregate all mismatches and report at the end. | 1. STATE_DB PORT_TABLE contains a `fec` field for the port.<br>2. Operational FEC mode in STATE_DB matches the configured FEC mode in CONFIG_DB.<br>3. Any mismatches (platform or driver silently ignoring configured FEC) are identified and logged. |
| 10 | Autoneg consistency: CONFIG_DB vs APPL_DB (orchagent applied) | 1. Retrieve the `expected_autoneg` attribute from PORT_CONFIG_ATTRIBUTES for the port.<br>2. If `expected_autoneg` is absent, skip the port.<br>3. Query `sonic-db-cli CONFIG_DB hget 'PORT\|<port>' autoneg` to retrieve the configured autoneg setting.<br>4. Query `sonic-db-cli APPL_DB hget 'PORT_TABLE:<port>' autoneg` to retrieve the value applied by orchagent to APPL_DB.<br>5. Compare CONFIG_DB and APPL_DB values.<br>6. Aggregate all mismatches and report at the end. | 1. APPL_DB PORT_TABLE contains an `autoneg` field for the port.<br>2. The autoneg value in APPL_DB matches the configured value in CONFIG_DB, confirming orchagent has applied the setting.<br>3. Any mismatches indicate that orchagent has not propagated the configuration correctly. |

## Cleanup and Post-Test Verification

The following steps are performed once after **all test cases** in this plan have completed. Per-test teardown (log scan) already covers ongoing health monitoring throughout the run.

### Post-Test Checks

1. **Port operational state**: Confirm all ports in `port_attributes_dict` remain operationally up. All tests are read-only DB queries so no link disruptions are expected, but this confirms the assumption.

### Post-Test Report Generation

1. **Test Summary**: Generate comprehensive test results including pass/fail status for each test case.
2. **Mismatch Report**: Summarize all configuration mismatches (speed, FEC, MTU, autoneg, DOM polling, cross-layer consistency failures) with actual vs. expected values, the DB source of each field, and the port where the mismatch was detected.

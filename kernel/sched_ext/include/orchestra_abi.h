/* SPDX-License-Identifier: GPL-2.0 */
#ifndef ORCHESTRA_ABI_H
#define ORCHESTRA_ABI_H

/*
 * Canonical ORCHESTRA C <-> BPF ABI.
 *
 * This header deliberately contains only fixed-width integer constants and
 * enums.  The numeric action IDs are the research action IDs and the wire
 * action IDs; producers must still translate through an explicit switch so
 * that an invalid enum can never be passed through as an action.
 */
#define ORCHESTRA_ABI_MAGIC          0x4f524342u /* "ORCB" */
#define ORCHESTRA_ABI_VERSION        2u
#define ORCHESTRA_ABI_SCHEMA_VERSION 2u
#define ORCHESTRA_SCX_API_VERSION     61200u /* upstream Linux 6.12 semantics */

enum orchestra_action_id {
    ORCHESTRA_ACTION_RUN = 0,
    ORCHESTRA_ACTION_SLEEP = 1,
    ORCHESTRA_ACTION_MIGRATE = 2,
    ORCHESTRA_ACTION_THROTTLE = 3,
    ORCHESTRA_ACTION_YIELD = 4,
    ORCHESTRA_ACTION_COUNT = 5
};

enum orchestra_controller_state {
    ORCHESTRA_CTRL_NORMAL = 0,
    ORCHESTRA_CTRL_DEGRADED = 1,
    ORCHESTRA_CTRL_SATURATED = 2,
    ORCHESTRA_CTRL_DISABLED = 3,
    ORCHESTRA_CTRL_ROLLBACK = 4,
    ORCHESTRA_CTRL_RECOVERY = 5,
    ORCHESTRA_CTRL_COUNT = 6
};

enum orchestra_policy_mode {
    ORCHESTRA_POLICY_TRAIN = 0,
    ORCHESTRA_POLICY_ADAPT = 1,
    ORCHESTRA_POLICY_EVALUATE = 2,
    ORCHESTRA_POLICY_COUNT = 3
};

#define ORCHESTRA_CPU_ANY 0xffffffffu

#endif /* ORCHESTRA_ABI_H */

#include "imu_checked.h"

static bmi2_dev* device=nullptr;
static int8_t initialization=BMI2_E_NULL_PTR;
static bool configured=false;
extern "C" int8_t __real_bmi270_init(bmi2_dev*);
extern "C" int8_t __wrap_bmi270_init(bmi2_dev* candidate) {
    device=nullptr;configured=false;
    initialization=__real_bmi270_init(candidate);
    if (initialization==BMI2_OK) device=candidate;
    return initialization;
}
int8_t imu_configure_checked() {
    configured=false;
    if (initialization!=BMI2_OK) return initialization;
    if (!device) return BMI2_E_NULL_PTR;
    bmi2_sens_config config[2]{};
    config[0].type=BMI2_ACCEL;config[1].type=BMI2_GYRO;
    auto result=bmi2_get_sensor_config(config,2,device);
    if (result!=BMI2_OK) return result;
    config[0].cfg.acc.odr=BMI2_ACC_ODR_200HZ;
    config[0].cfg.acc.range=BMI2_ACC_RANGE_4G;
    config[1].cfg.gyr.odr=BMI2_GYR_ODR_200HZ;
    config[1].cfg.gyr.range=BMI2_GYR_RANGE_1000;
    result=bmi270_set_sensor_config(config,2,device);
    if (result!=BMI2_OK) return result;
    const uint8_t sensors[]{BMI2_ACCEL,BMI2_GYRO};
    result=bmi270_sensor_enable(sensors,2,device);
    if (result!=BMI2_OK) return result;
    result=bmi2_get_sensor_config(config,2,device);
    if (result!=BMI2_OK) return result;
    if (config[0].cfg.acc.odr!=BMI2_ACC_ODR_200HZ || config[0].cfg.acc.range!=BMI2_ACC_RANGE_4G
        || config[1].cfg.gyr.odr!=BMI2_GYR_ODR_200HZ || config[1].cfg.gyr.range!=BMI2_GYR_RANGE_1000)
        return BMI2_E_INVALID_STATUS;
    configured=true;return BMI2_OK;
}
int8_t imu_read_checked(bmi2_sens_data& output) {
    if (!device || !configured) return BMI2_E_INVALID_STATUS;
    bmi2_sens_data candidate{};
    auto result=bmi2_get_sensor_data(&candidate,device);
    if (result==BMI2_OK) output=candidate;
    return result;
}

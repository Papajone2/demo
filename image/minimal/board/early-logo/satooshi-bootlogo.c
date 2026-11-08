// SPDX-License-Identifier: GPL-2.0-only
/*
 * Original Pi Zero W/WH + 128x64 SSD1306 bonnet, I2C1 address 0x3c.
 * One public frame during built-in driver initialization, before root mount.
 * No persistent device/client ownership, private data, retries or boot failure.
 */
#include <linux/errno.h>
#include <linux/i2c.h>
#include <linux/init.h>
#include <linux/kobject.h>
#include <linux/ktime.h>
#include <linux/math64.h>
#include <linux/printk.h>
#include <linux/string.h>
#include <linux/sysfs.h>
#include <linux/types.h>
#include <linux/timekeeping.h>

#include "satooshi-bootlogo-bitmap.h"

static bool enabled __initdata = true;
static bool attempted __initdata;
static u64 logo_ms;

static int __init logo_setting(char *value)
{
	if (!strcmp(value, "0"))
		enabled = false;
	else if (strcmp(value, "1"))
		return 0;
	return 1;
}
__setup("satooshi_logo=", logo_setting);

static ssize_t satooshi_logo_ms_show(struct kobject *kobj,
				    struct kobj_attribute *attr, char *buf)
{
	return sysfs_emit(buf, "%llu\n", (unsigned long long)logo_ms);
}
static struct kobj_attribute logo_attribute = __ATTR_RO(satooshi_logo_ms);

static int __init logo_write(struct i2c_adapter *adapter,
			    const u8 *bytes, u16 length)
{
	struct i2c_msg message = {
		.addr = 0x3c,
		.flags = 0,
		.len = length,
		.buf = (u8 *)bytes,
	};
	int result = i2c_transfer(adapter, &message, 1);

	return result == 1 ? 0 : result < 0 ? result : -EIO;
}

static int __init draw_logo(struct i2c_adapter *adapter)
{
	/* Keep the display off until its complete frame is ready: no garbage flash. */
	static const u8 commands[] __initconst = {
		0x00, 0xae, 0xd5, 0x80, 0xa8, 0x3f, 0xd3, 0x00, 0x40,
		0x8d, 0x14, 0x20, 0x00, 0xa1, 0xc8, 0xda, 0x12,
		0x81, 0x7f, 0xd9, 0xf1, 0xdb, 0x40, 0xa4, 0xa6,
		0x21, 0x00, 127, 0x22, 0x00, 7,
	};
	static const u8 display_on[] __initconst = { 0x00, 0xaf };
	u8 packet[33];
	unsigned int offset;
	int result;

	result = logo_write(adapter, commands, sizeof(commands));
	if (result)
		return result;
	/* Known bonnet-compatible 32-byte chunks, without a large kernel stack buffer. */
	packet[0] = 0x40;
	for (offset = 0; offset < sizeof(satooshi_logo_frame); offset += 32) {
		memcpy(packet + 1, satooshi_logo_frame + offset, 32);
		result = logo_write(adapter, packet, sizeof(packet));
		if (result)
			return result;
	}
	return logo_write(adapter, display_on, sizeof(display_on));
}

static int __init satooshi_early_logo_init(void)
{
	struct i2c_adapter *adapter;
	int result;

	if (!enabled || attempted)
		return 0;
	adapter = i2c_get_adapter(1);
	if (!adapter) {
		pr_info("SATOOSHI_BOOT stage=logo_kernel_unavailable\n");
		return 0; /* Userspace renderer retries when the bus is available. */
	}
	attempted = true;
	result = draw_logo(adapter);
	i2c_put_adapter(adapter);
	if (result) {
		pr_warn("SATOOSHI_BOOT stage=logo_kernel_failed error=%d\n", result);
		return 0;
	}
	logo_ms = div_u64(ktime_get_boottime_ns(), 1000000);
	pr_info("SATOOSHI_BOOT stage=logo_kernel kernel_milliseconds=%llu\n",
		(unsigned long long)logo_ms);
	result = sysfs_create_file(kernel_kobj, &logo_attribute.attr);
	if (result)
		pr_warn("Satooshi early logo timing attribute unavailable: %d\n", result);
	return 0;
}
/* First opportunity after built-in device drivers; no root filesystem needed. */
device_initcall_sync(satooshi_early_logo_init);

static int __init satooshi_early_logo_late_init(void)
{
	/* A deferred I2C adapter gets one later opportunity, without waiting/sleeping.
	 * Never repeat a completed or failed bus transfer during kernel startup.
	 */
	return satooshi_early_logo_init();
}
late_initcall_sync(satooshi_early_logo_late_init);

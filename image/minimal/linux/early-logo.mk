# Dependencies are configured before PRE_BUILD hooks. Use the host interpreter
# captured before Buildroot changes PATH; Pillow is in firmware requirements.
SATOOSHI_LOGO_PYTHON ?= /usr/bin/python3
define SATOOSHI_INSTALL_KERNEL_LOGO
	$(SATOOSHI_LOGO_PYTHON) \
		"$(BR2_EXTERNAL_SATOOSHI_PATH)/board/early-logo/make-logo.py" \
		"$(SATOOSHI_FIRMWARE_DIR)/device/satooshi/assets/wordmark.png" \
		"$(@D)/init/satooshi-bootlogo-bitmap.h"
	$(INSTALL) -m 0644 \
		"$(BR2_EXTERNAL_SATOOSHI_PATH)/board/early-logo/satooshi-bootlogo.c" \
		"$(@D)/init/satooshi-bootlogo.c"
	grep -qF 'obj-y += satooshi-bootlogo.o' "$(@D)/init/Makefile" || \
		printf '\nobj-y += satooshi-bootlogo.o\n' >>"$(@D)/init/Makefile"
endef
LINUX_PRE_BUILD_HOOKS += SATOOSHI_INSTALL_KERNEL_LOGO

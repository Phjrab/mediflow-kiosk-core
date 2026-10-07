import os
import unittest
from unittest import mock

import numpy as np


os.environ.setdefault('TORCH_DEVICE', 'cpu')

from utils import uvc_camera


class UvcCameraTest(unittest.TestCase):
    @mock.patch.object(uvc_camera, 'opencv_has_gstreamer', return_value=False)
    @mock.patch.object(uvc_camera.time, 'sleep')
    @mock.patch.object(uvc_camera.cv2, 'VideoCapture')
    def test_requires_a_real_frame_and_releases_failed_backend(
        self,
        video_capture,
        _sleep,
        _gstreamer,
    ):
        first = mock.Mock()
        first.isOpened.return_value = True
        first.read.return_value = (False, None)

        second = mock.Mock()
        second.isOpened.return_value = True
        second.read.return_value = (True, np.zeros((480, 640, 3), dtype=np.uint8))
        second.get.return_value = 0
        video_capture.side_effect = [first, second]

        capture, frame, metadata = uvc_camera.open_usb_uvc_camera(
            0,
            gstreamer_pipeline=lambda _index: 'unused',
            frame_attempts=1,
        )

        self.assertIs(capture, second)
        self.assertEqual(frame.shape, (480, 640, 3))
        self.assertEqual(metadata['backend'], 'v4l2-path')
        first.release.assert_called_once_with()
        self.assertEqual(
            video_capture.call_args_list,
            [
                mock.call(0, uvc_camera.cv2.CAP_V4L2),
                mock.call('/dev/video0', uvc_camera.cv2.CAP_V4L2),
            ],
        )

    def test_negative_index_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'non-negative'):
            uvc_camera.open_usb_uvc_camera(-1)

    @mock.patch.object(uvc_camera.os.path, 'exists', return_value=True)
    @mock.patch.object(uvc_camera.os, 'access', return_value=False)
    @mock.patch.object(uvc_camera.cv2, 'VideoCapture')
    def test_permission_denied_does_not_open_device(self, capture, access, exists):
        with self.assertRaisesRegex(uvc_camera.UvcCameraError, 'permission_denied'):
            uvc_camera.open_usb_uvc_camera(0)
        capture.assert_not_called()


if __name__ == '__main__':
    unittest.main()

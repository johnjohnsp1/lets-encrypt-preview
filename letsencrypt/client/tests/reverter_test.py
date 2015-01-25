"""Test letsencrypt.client.reverter."""
import logging
import os
import shutil
import tempfile
import unittest

import mock


# pylint: disable=invalid-name,protected-access,too-many-instance-attributes
class ReverterCheckpointLocalTest(unittest.TestCase):
    """Test the Reverter Class."""
    def setUp(self):
        from letsencrypt.client.reverter import Reverter

        # Disable spurious errors... we are trying to test for them
        logging.disable(logging.CRITICAL)

        self.work_dir, self.direc = setup_work_direc()

        self.reverter = Reverter(self.direc)

        tup = setup_test_files()
        self.config1, self.config2, self.dir1, self.dir2, self.sets = tup

    def tearDown(self):
        shutil.rmtree(self.work_dir)
        shutil.rmtree(self.dir1)
        shutil.rmtree(self.dir2)

    def test_basic_add_to_temp_checkpoint(self):
        # These shouldn't conflict even though they are both named config.txt
        self.reverter.add_to_temp_checkpoint(self.sets[0], "save1")
        self.reverter.add_to_temp_checkpoint(self.sets[1], "save2")

        self.assertTrue(os.path.isdir(self.reverter.direc['temp']))
        self.assertEqual(get_save_notes(self.direc['temp']), "save1save2")
        self.assertFalse(os.path.isfile(
            os.path.join(self.direc['temp'], "NEW_FILES")))

        self.assertEqual(
            get_filepaths(self.direc['temp']),
            "{0}\n{1}\n".format(self.config1, self.config2))

    def test_add_to_checkpoint_copy_failure(self):
        from letsencrypt.client.errors import LetsEncryptReverterError

        with mock.patch("letsencrypt.client.reverter."
                        "shutil.copy2") as mock_copy2:
            mock_copy2.side_effect = IOError("bad copy")
            self.assertRaises(LetsEncryptReverterError,
                              self.reverter.add_to_checkpoint,
                              self.sets[0],
                              "save1")

    def test_checkpoint_conflict(self):
        """Make sure that checkpoint errors are thrown appropriately."""
        from letsencrypt.client.errors import LetsEncryptReverterError

        config3 = os.path.join(self.dir1, "config3.txt")
        self.reverter.register_file_creation(True, config3)
        update_file(config3, "This is a new file!")

        self.reverter.add_to_checkpoint(self.sets[2], "save1")
        # This shouldn't throw an error
        self.reverter.add_to_temp_checkpoint(self.sets[0], "save2")
        # Raise error
        self.assertRaises(
            LetsEncryptReverterError, self.reverter.add_to_checkpoint,
            self.sets[2], "save3")
        # Should not cause an error
        self.reverter.add_to_checkpoint(self.sets[1], "save4")

        # Check to make sure new files are also checked...
        self.assertRaises(
            LetsEncryptReverterError,
            self.reverter.add_to_checkpoint,
            set([config3]), "invalid save")

    def test_multiple_saves_and_temp_revert(self):
        self.reverter.add_to_temp_checkpoint(self.sets[0], "save1")
        update_file(self.config1, "updated-directive")
        self.reverter.add_to_temp_checkpoint(self.sets[0], "save2-updated dir")
        update_file(self.config1, "new directive change that we won't keep")

        self.reverter.revert_temporary_config()
        self.assertEqual(read_in(self.config1), "directive-dir1")

    def test_multiple_registration_fail_and_revert(self):
        config3 = os.path.join(self.dir1, "config3.txt")
        update_file(config3, "Config3")
        config4 = os.path.join(self.dir2, "config4.txt")
        update_file(config4, "Config4")

        # Test multiple registrations and two registrations at once
        self.reverter.register_file_creation(True, self.config1)
        self.reverter.register_file_creation(True, self.config2)
        self.reverter.register_file_creation(True, config3, config4)

        # Simulate Let's Encrypt crash... recovery routine is run
        self.reverter.recovery_routine()

        self.assertFalse(os.path.isfile(self.config1))
        self.assertFalse(os.path.isfile(self.config2))
        self.assertFalse(os.path.isfile(config3))
        self.assertFalse(os.path.isfile(config4))

    def test_multiple_registration_same_file(self):
        self.reverter.register_file_creation(True, self.config1)
        self.reverter.register_file_creation(True, self.config1)
        self.reverter.register_file_creation(True, self.config1)
        self.reverter.register_file_creation(True, self.config1)

        files = get_new_files(self.direc['temp'])

        self.assertEqual(len(files), 1)

    def test_register_file_creation_write_error(self):
        from letsencrypt.client.errors import LetsEncryptReverterError

        m_open = mock.mock_open()
        with mock.patch("letsencrypt.client.reverter.open",
                        m_open, create=True):
            m_open.side_effect = OSError("bad open")
            self.assertRaises(LetsEncryptReverterError,
                              self.reverter.register_file_creation,
                              True, self.config1)

    def test_bad_registration(self):
        from letsencrypt.client.errors import LetsEncryptReverterError
        # Made this mistake and want to make sure it doesn't happen again...
        self.assertRaises(LetsEncryptReverterError,
                          self.reverter.register_file_creation,
                          "filepath")

    def test_recovery_routine_in_progress_failure(self):
        from letsencrypt.client.errors import LetsEncryptReverterError
        self.reverter.add_to_checkpoint(self.sets[0], "perm save")

        self.reverter._recover_checkpoint = mock.MagicMock(
            side_effect=LetsEncryptReverterError)
        self.assertRaises(LetsEncryptReverterError,
                          self.reverter.recovery_routine)

    def test_recover_checkpoint_revert_temp_failures(self):
        from letsencrypt.client.errors import LetsEncryptReverterError

        mock_recover = mock.MagicMock(side_effect=LetsEncryptReverterError("e"))
        self.reverter._recover_checkpoint = mock_recover

        self.reverter.add_to_temp_checkpoint(self.sets[0], "config1 save")

        self.assertRaises(LetsEncryptReverterError,
                          self.reverter.revert_temporary_config)

    def test_recover_checkpoint_rollback_failure(self):
        from letsencrypt.client.errors import LetsEncryptReverterError

        mock_recover = mock.MagicMock(side_effect=LetsEncryptReverterError("e"))
        self.reverter._recover_checkpoint = mock_recover

        self.reverter.add_to_checkpoint(self.sets[0], "config1 save")
        self.reverter.finalize_checkpoint("Title")

        self.assertRaises(LetsEncryptReverterError,
                          self.reverter.rollback_checkpoints, 1)

    def test_recover_checkpoint_copy_failure(self):
        from letsencrypt.client.errors import LetsEncryptReverterError

        self.reverter.add_to_temp_checkpoint(self.sets[0], "save1")

        with mock.patch("letsencrypt.client.reverter.shutil."
                        "copy2") as mock_copy2:
            mock_copy2.side_effect = OSError("bad copy")
            self.assertRaises(LetsEncryptReverterError,
                              self.reverter.revert_temporary_config)

    def test_recover_checkpoint_rm_failure(self):
        from letsencrypt.client.errors import LetsEncryptReverterError

        self.reverter.add_to_temp_checkpoint(self.sets[0], "temp save")

        with mock.patch("letsencrypt.client.reverter.shutil."
                        "rmtree") as mock_rmtree:
            mock_rmtree.side_effect = OSError("Cannot remove tree")
            self.assertRaises(LetsEncryptReverterError,
                              self.reverter.revert_temporary_config)

    @mock.patch("letsencrypt.client.reverter.logging.warning")
    def test_recover_checkpoint_missing_new_files(self, mock_warn):
        self.reverter.register_file_creation(
            True, os.path.join(self.dir1, "missing_file.txt"))
        self.reverter.revert_temporary_config()
        self.assertEqual(mock_warn.call_count, 1)

    @mock.patch("letsencrypt.client.reverter.os.remove")
    def test_recover_checkpoint_remove_failure(self, mock_remove):
        from letsencrypt.client.errors import LetsEncryptReverterError

        self.reverter.register_file_creation(True, self.config1)
        mock_remove.side_effect = OSError("Can't remove")
        self.assertRaises(LetsEncryptReverterError,
                          self.reverter.revert_temporary_config)

    def test_recovery_routine_temp_and_perm(self):
        # Register a new perm checkpoint file
        config3 = os.path.join(self.dir1, "config3.txt")
        self.reverter.register_file_creation(False, config3)
        update_file(config3, "This is a new perm file!")

        # Add changes to perm checkpoint
        self.reverter.add_to_checkpoint(self.sets[0], "perm save1")
        update_file(self.config1, "updated perm config1")
        self.reverter.add_to_checkpoint(self.sets[1], "perm save2")
        update_file(self.config2, "updated perm config2")

        # Add changes to a temporary checkpoint
        self.reverter.add_to_temp_checkpoint(self.sets[0], "temp save1")
        update_file(self.config1, "second update now temp config1")

        # Register a new temp checkpoint file
        config4 = os.path.join(self.dir2, "config4.txt")
        self.reverter.register_file_creation(True, config4)
        update_file(config4, "New temporary file!")

        # Now erase everything
        self.reverter.recovery_routine()

        # Now Run tests
        # These were new files.. they should be removed
        self.assertFalse(os.path.isfile(config3))
        self.assertFalse(os.path.isfile(config4))

        # Check to make sure everything got rolled back appropriately
        self.assertEqual(read_in(self.config1), "directive-dir1")
        self.assertEqual(read_in(self.config2), "directive-dir2")

# pylint: disable=invalid-name,protected-access,too-many-instance-attributes
class TestFullCheckpointsReverter(unittest.TestCase):
    """Tests functions having to deal with full checkpoints."""
    def setUp(self):
        from letsencrypt.client.reverter import Reverter
        # Disable spurious errors...
        logging.disable(logging.CRITICAL)

        self.work_dir, self.direc = setup_work_direc()
        self.reverter = Reverter(self.direc)

        tup = setup_test_files()
        self.config1, self.config2, self.dir1, self.dir2, self.sets = tup

    def tearDown(self):
        shutil.rmtree(self.work_dir)
        shutil.rmtree(self.dir1)
        shutil.rmtree(self.dir2)

    def test_rollback_improper_inputs(self):
        from letsencrypt.client.errors import LetsEncryptReverterError
        self.assertRaises(
            LetsEncryptReverterError,
            self.reverter.rollback_checkpoints, "-1")
        self.assertRaises(
            LetsEncryptReverterError,
            self.reverter.rollback_checkpoints, -1000)
        self.assertRaises(
            LetsEncryptReverterError,
            self.reverter.rollback_checkpoints, "one")

    def test_rollback_finalize_checkpoint_valid_inputs(self):
        config3 = self._setup_three_checkpoints()

        # Check resulting backup directory
        self.assertEqual(len(os.listdir(self.direc['backup'])), 3)
        # Check rollbacks
        # First rollback
        self.reverter.rollback_checkpoints(1)
        self.assertEqual(read_in(self.config1), "update config1")
        self.assertEqual(read_in(self.config2), "update config2")
        # config3 was not included in checkpoint
        self.assertEqual(read_in(config3), "Final form config3")

        # Second rollback
        self.reverter.rollback_checkpoints(1)
        self.assertEqual(read_in(self.config1), "update config1")
        self.assertEqual(read_in(self.config2), "directive-dir2")
        self.assertFalse(os.path.isfile(config3))

        # One dir left... check title
        all_dirs = os.listdir(self.direc['backup'])
        self.assertEqual(len(all_dirs), 1)
        self.assertTrue(
            "First Checkpoint" in get_save_notes(
                os.path.join(self.direc['backup'], all_dirs[0])))
        # Final rollback
        self.reverter.rollback_checkpoints(1)
        self.assertEqual(read_in(self.config1), "directive-dir1")

    @mock.patch("letsencrypt.client.reverter.logging.warning")
    def test_finalize_checkpoint_no_in_progress(self, mock_warn):
        self.reverter.finalize_checkpoint("No checkpoint... should warn")
        self.assertEqual(mock_warn.call_count, 1)

    @mock.patch("letsencrypt.client.reverter.shutil.move")
    def test_finalize_checkpoint_cannot_title(self, mock_move):
        from letsencrypt.client.errors import LetsEncryptReverterError

        self.reverter.add_to_checkpoint(self.sets[0], "perm save")
        mock_move.side_effect = OSError("cannot move")

        self.assertRaises(LetsEncryptReverterError,
                          self.reverter.finalize_checkpoint,
                          "Title")

    @mock.patch("letsencrypt.client.reverter.os.rename")
    def test_finalize_checkpoint_no_rename_directory(self, mock_rename):
        from letsencrypt.client.errors import LetsEncryptReverterError

        self.reverter.add_to_checkpoint(self.sets[0], "perm save")
        mock_rename.side_effect = OSError

        self.assertRaises(LetsEncryptReverterError,
                          self.reverter.finalize_checkpoint,
                          "Title")

    @mock.patch("letsencrypt.client.reverter.logging")
    def test_rollback_too_many(self, mock_logging):
        self.reverter.rollback_checkpoints(1)
        self.assertEqual(mock_logging.warning.call_count, 1)

    def test_multi_rollback(self):
        config3 = self._setup_three_checkpoints()
        self.reverter.rollback_checkpoints(3)

        self.assertEqual(read_in(self.config1), "directive-dir1")
        self.assertEqual(read_in(self.config2), "directive-dir2")
        self.assertFalse(os.path.isfile(config3))

    def test_view_config_changes(self):
        """This is not strict as this is subject to change."""
        self._setup_three_checkpoints()
        # Just make sure it doesn't throw any errors.
        self.reverter.view_config_changes()

    @mock.patch("letsencrypt.client.reverter.logging")
    def test_view_config_changes_no_backups(self, mock_logging):
        self.reverter.view_config_changes()
        self.assertTrue(mock_logging.info.call_count > 0)

    def test_view_config_changes_bad_backups_dir(self):
        from letsencrypt.client.errors import LetsEncryptReverterError
        # There shouldn't be any "in progess directories when this is called
        # It must just be clean checkpoints
        os.makedirs(os.path.join(self.direc['backup'], "in_progress"))

        self.assertRaises(LetsEncryptReverterError,
                          self.reverter.view_config_changes)

    def _setup_three_checkpoints(self):
        """Generate some finalized checkpoints."""
        # Checkpoint1 - config1
        self.reverter.add_to_checkpoint(self.sets[0], "first save")
        self.reverter.finalize_checkpoint("First Checkpoint")

        update_file(self.config1, "update config1")

        # Checkpoint2 - new file config3, update config2
        config3 = os.path.join(self.dir1, "config3.txt")
        self.reverter.register_file_creation(False, config3)
        update_file(config3, "directive-config3")
        self.reverter.add_to_checkpoint(self.sets[1], "second save")
        self.reverter.finalize_checkpoint("Second Checkpoint")

        update_file(self.config2, "update config2")
        update_file(config3, "update config3")

        # Checkpoint3 - update config1, config2
        self.reverter.add_to_checkpoint(self.sets[2], "third save")
        self.reverter.finalize_checkpoint("Third Checkpoint - Save both")

        update_file(self.config1, "Final form config1")
        update_file(self.config2, "Final form config2")
        update_file(config3, "Final form config3")

        return config3


class QuickInitReverterTest(unittest.TestCase):
    """Quick test of init."""
    def test_init(self):
        from letsencrypt.client.reverter import Reverter
        rev = Reverter()

        # Verify direc is set
        self.assertTrue(rev.direc['backup'])
        self.assertTrue(rev.direc['temp'])
        self.assertTrue(rev.direc['progress'])


def setup_work_direc():
    """Setup directories."""
    work_dir = tempfile.mkdtemp("work")
    backup = os.path.join(work_dir, "backup")
    os.makedirs(backup)
    direc = {'backup': backup,
             'temp': os.path.join(work_dir, "temp"),
             'progress': os.path.join(backup, "progress")}

    return work_dir, direc


def setup_test_files():
    """Setup sample configuration files."""
    dir1 = tempfile.mkdtemp("dir1")
    dir2 = tempfile.mkdtemp("dir2")
    config1 = os.path.join(dir1, "config.txt")
    config2 = os.path.join(dir2, "config.txt")
    with open(config1, 'w') as file_fd:
        file_fd.write("directive-dir1")
    with open(config2, 'w') as file_fd:
        file_fd.write("directive-dir2")

    sets = [set([config1]),
            set([config2]),
            set([config1, config2])]

    return config1, config2, dir1, dir2, sets


def get_save_notes(dire):
    """Read save notes"""
    return read_in(os.path.join(dire, 'CHANGES_SINCE'))


def get_filepaths(dire):
    """Get Filepaths"""
    return read_in(os.path.join(dire, 'FILEPATHS'))


def get_new_files(dire):
    """Get new files."""
    return read_in(os.path.join(dire, 'NEW_FILES')).splitlines()


def read_in(path):
    """Read in a file, return the str"""
    with open(path, 'r') as file_fd:
        return file_fd.read()


def update_file(filename, string):
    """Update a file with a new value."""
    with open(filename, 'w') as file_fd:
        file_fd.write(string)


if __name__ == '__main__':
    unittest.main()
import os
import sys
import subprocess

from neatlynx.dvc_path import DvcPath
from neatlynx.exceptions import NeatLynxException
from neatlynx.logger import Logger
from neatlynx.config import Config


class GitCmdError(NeatLynxException):
    def __init__(self, msg):
        NeatLynxException.__init__(self, msg)


class GitWrapperI(object):
    def __init__(self, git_dir=None, commit=None):
        self._git_dir = git_dir
        self._commit = commit

    @property
    def git_dir(self):
        return self._git_dir

    @property
    def git_dir_abs(self):
        return os.path.realpath(self.git_dir)

    @property
    def curr_dir_abs(self):
        return os.path.abspath(os.curdir)

    @property
    def curr_commit(self):
        return self._commit

    def build_dvc_path(self, relative):
        return DvcPath(relative, self.git_dir_abs, self.curr_dir_abs)


class GitWrapper(GitWrapperI):
    def __init__(self):
        GitWrapperI.__init__(self)

    @staticmethod
    def exec_cmd(cmd, stdout_file=None, stderr_file=None, cwd=None):
        stdout_fd = None
        if stdout_file is not None:
            if stdout_file == '-':
                stdout = sys.stdout
            else:
                stdout_fd = open(stdout_file, 'w')
                stdout = stdout_fd
        else:
            stdout = subprocess.PIPE

        stderr_fd = None
        if stderr_file is not None:
            if stderr_file == '-':
                stderr = sys.stderr
            else:
                stderr_fd = open(stderr_file, 'w')
                stderr = stderr_fd
        else:
            stderr = subprocess.PIPE

        p = subprocess.Popen(cmd, cwd=cwd,
                             stdout=stdout,
                             stderr=stderr)
        out, err = map(lambda s: s.decode().strip('\n\r') if s else '', p.communicate())

        if stderr_fd:
            stderr_fd.close()
        if stdout_fd:
            stdout_fd.close()

        return p.returncode, out, err

    @staticmethod
    def exec_cmd_only_success(cmd, stdout_file=None, stderr_file=None, cwd=None):
        code, out, err = GitWrapper.exec_cmd(cmd, stdout_file=stdout_file, stderr_file=stderr_file, cwd=cwd)
        if code != 0:
            if err:
                sys.stderr.write(err + '\n')
            raise GitCmdError('Git command error ({}):\n{}'.format(' '.join(cmd), out))
        return out

    def is_ready_to_go(self):
        statuses = self.status_files()
        if len(statuses) > 0:
            Logger.error('Commit all changed files before running reproducible command.')
            Logger.error('Changed files:')
            for status, file in statuses:
                Logger.error("{} {}".format(status, file))
            return False

        return True

    @property
    def curr_dir_nlx(self):
        return os.path.relpath(self.curr_dir_abs, self.git_dir_abs)

    @property
    def git_dir(self):
        if self._git_dir:
            return self._git_dir

        try:
            code, out, err = GitWrapper.exec_cmd(['git', 'rev-parse', '--show-toplevel'])

            if code != 0:
                raise GitCmdError('Git command error - {}'.format(err))

            self._git_dir = out
            return self._git_dir
        except GitCmdError:
            raise
        except Exception as e:
            raise GitCmdError('Unable to run git command: {}'.format(e))
        pass

    @staticmethod
    def status_files():
        code, out, err = GitWrapper.exec_cmd(['git', 'status', '--porcelain'])
        if code != 0:
            raise GitCmdError('Git command error - {}'.format(err))

        return GitWrapper.parse_porcelain_files(out)

    @staticmethod
    def parse_porcelain_files(out):
        result = []
        if len(out) > 0:
            lines = out.split('\n')
            for line in lines:
                status = line[:2]
                file = line[3:]
                result.append((status, file))
        return result

    @property
    def curr_commit(self):
        if self._commit is None:
            code, out, err = GitWrapper.exec_cmd(['git', 'rev-parse', '--short', 'HEAD'])
            if code != 0:
                raise GitCmdError('Git command error - {}'.format(err))
            self._commit = out
        return self._commit

    def commit_all_changes(self, message):
        GitWrapper.exec_cmd_only_success(['git', 'add', '--all'])
        out_status = GitWrapper.exec_cmd_only_success(['git', 'status', '--porcelain'])
        GitWrapper.exec_cmd_only_success(['git', 'commit', '-m', message])
        return GitWrapper.parse_porcelain_files(out_status)

    def commit_all_changes_and_log_status(self, message):
        statuses = self.commit_all_changes(message)
        Logger.printing('A new commit {} was made in the current branch. Added files:'.format(self.curr_commit))
        for status, file in statuses:
            Logger.printing('\t{} {}'.format(status, file))
        pass

    @property
    def lock_file(self):
        return os.path.join(self.git_dir_abs, '.' + Config.CONFIG + '.lock')

    @staticmethod
    def abs_paths_to_relative(files):
        cur_dir = os.path.realpath(os.curdir)

        result = []
        for file in files:
            result.append(os.path.relpath(os.path.realpath(file), cur_dir))

        return result

    def abs_paths_to_nlx(self, files):
        result = []
        for file in files:
            result.append(os.path.relpath(os.path.abspath(file), self.git_dir_abs))

        return result

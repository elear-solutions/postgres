from conans import ConanFile, AutoToolsBuildEnvironment, tools
from conans.errors import ConanInvalidConfiguration
import os
import glob


class LibpqConan(ConanFile):
    name = "postgreSQL"
    version = "0.0.1"
    description = "The library used by all the standard PostgreSQL tools."
    topics = ("conan", "libpq", "postgresql", "database", "db")
    url = "https://github.com/elear-solutions/postgres"
    license = "PostgreSQL"
    settings = "os", "arch", "compiler", "build_type"
    options = {
        "shared": [True, False],
        "fPIC": [True, False],
        "with_zlib": [True, False, "deprecated"],
        "with_openssl": [True, False],
        "disable_rpath": [True, False]
    }
    default_options = {
        'shared': False,
        'fPIC': True,
        'with_zlib': "deprecated",
        'with_openssl': False,
        'disable_rpath': False
    }
    default_user = "jenkins"
    default_channel = "master"
    _autotools = None

    @property
    def _source_subfolder(self):
        return ".."

    def configure(self):
        if self.options.with_zlib != "deprecated":
            self.output.warn("with_zlib option is deprecated, do not use anymore")
        del self.options.with_zlib

    def requirements(self):
        if self.options.with_openssl:
            self.requires("openssl/1.1.1h")
        if self.user and self.channel:
            default_user = self.user
            default_channel = self.channel
        self.requires("bison/[~0.0.1]@%s/%s" % (default_user, default_channel))

    def source(self):
        tools.get(**self.conan_data["sources"][self.version])
        extracted_dir = "postgresql-" + self.version
        os.rename(extracted_dir, self._source_subfolder)

    def _configure_autotools(self):
        if not self._autotools:
            self._autotools = AutoToolsBuildEnvironment(self)
            args = ['--without-readline']
            args.append('--without-zlib')
            args.append('--with-openssl' if self.options.with_openssl else '--without-openssl')
            with tools.chdir(".."):
                self._autotools.configure(args=args)
        return self._autotools

    @property
    def _make_args(self):
        args = []

    def build(self):
        autotools = self._configure_autotools()
        with tools.chdir(os.path.join(self._source_subfolder, "src", "backend")):
            autotools.make(args=self._make_args, target="..")
        with tools.chdir(os.path.join(self._source_subfolder, "src", "common")):
            autotools.make(args=self._make_args)
        with tools.chdir(os.path.join(self._source_subfolder, "src", "include")):
            autotools.make(args=self._make_args)
        with tools.chdir(os.path.join(self._source_subfolder, "src", "interfaces", "libpq")):
            autotools.make(args=self._make_args)
        with tools.chdir(os.path.join(self._source_subfolder, "src", "bin", "pg_config")):
            autotools.make(args=self._make_args)

    def package(self):
            self.copy("*.h", dst="include", src="src/interfaces/libpq/")
            self.copy("*.h", dst="include", src="src/include/")
            # By default, files are copied recursively. To avoid that we are specifying keep_path=False
            self.copy("*.so*", dst="lib", src="src/interfaces/libpq/", keep_path=False)



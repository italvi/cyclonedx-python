# encoding: utf-8

# This file is part of CycloneDX Python Lib
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) OWASP Foundation. All Rights Reserved.

from enum import Enum, unique

from cyclonedx.exception.model import CycloneDxModelException
from cyclonedx.model import ExternalReference, ExternalReferenceType, HashType, Property, XsUri
from cyclonedx.model.component import Component
from cyclonedx.parser import BaseParser
from cyclonedx.model.bom import BomMetaData

# See https://github.com/package-url/packageurl-python/issues/65
from packageurl import PackageURL  # type: ignore
from toml import loads as load_toml

from ._cdx_properties import Poetry as PoetryProps
from ._debug import DebugMessageCallback, quiet


@unique
class PoetryGroupWellknown(Enum):
    """Wellknown Poetry groups.
    See https://python-poetry.org/docs/managing-dependencies/#dependency-groups
    """
    Main = "main"
    Dev = "dev"


class PoetryParser(BaseParser):

    def __init__(
            self, poetry_lock_contents: str,
            use_purl_bom_ref: bool = False,
            *,
            debug_message: DebugMessageCallback = quiet,
            pyproject_toml_contents: str
    ) -> None:
        super().__init__()
        debug_message('init {}', self.__class__.__name__)

        debug_message('loading poetry_lock_contents')
        poetry_lock = load_toml(poetry_lock_contents)

        poetry_lock_metadata = poetry_lock['metadata']
        try:
            poetry_lock_version = tuple(int(p) for p in str(poetry_lock_metadata['lock-version']).split('.'))
        except Exception:
            poetry_lock_version = (0,)
        debug_message('detected poetry_lock_version: {!r}', poetry_lock_version)

        debug_message('processing poetry_lock')
        for package in poetry_lock['package']:
            debug_message('processing package: {!r}', package)

            purl = PackageURL(type='pypi', name=package['name'], version=package['version'])
            bom_ref = purl.to_string() if use_purl_bom_ref else None
            component = Component(
                name=package['name'], bom_ref=bom_ref, version=package['version'],
                purl=purl
            )
            package_category = package.get('category')
            if package_category:
                component.properties.add(Property(
                    name=PoetryProps.PackageGroup.value,
                    value=package_category))
            debug_message('detecting package_files')
            package_files = package['files'] \
                if poetry_lock_version >= (2,) \
                else poetry_lock_metadata['files'][package['name']]
            debug_message('processing package_files: {!r}', package_files)
            for file_metadata in package_files:
                debug_message('processing file_metadata: {!r}', file_metadata)
                try:
                    component.external_references.add(ExternalReference(
                        type=ExternalReferenceType.DISTRIBUTION,
                        url=XsUri(component.get_pypi_url()),
                        comment=f'Distribution file: {file_metadata["file"]}',
                        hashes=[HashType.from_composite_str(file_metadata['hash'])]
                    ))
                except CycloneDxModelException as error:
                    # @todo traceback and details to the output?
                    debug_message('Warning: suppressed {!r}', error)
                    del error
            self._components.append(component)
        
        if pyproject_toml_contents:
            poetry_toml = load_toml(pyproject_toml_contents)
            poetry_toml_metadata = poetry_toml.get('tool','').get('poetry','')
            metadata_component = Component(
                name=poetry_toml_metadata['name'], version=poetry_toml_metadata['version']
            )
            self._metadata = BomMetaData(component=metadata_component)


class PoetryFileParser(PoetryParser):

    def __init__(
            self, poetry_lock_filename: str,
            use_purl_bom_ref: bool = False,
            *,
            debug_message: DebugMessageCallback = quiet,
            poetry_toml_filename: str = ""
    ) -> None:
        debug_message('open file: {}', poetry_lock_filename)
        with open(poetry_lock_filename) as plf:
            super(PoetryFileParser, self).__init__(
                poetry_lock_contents=plf.read(),
                use_purl_bom_ref=use_purl_bom_ref,
                debug_message=debug_message,
                pyproject_toml_contents=open(poetry_toml_filename).read()
            )

#!/usr/bin/python3
# -*- coding: utf-8 -*-
from collections import OrderedDict
from contextlib import contextmanager
import re
import sys
from xml.etree import ElementTree as etree
from xml.sax.saxutils import escape

import pywikibot


def do_pywikibot_patches():
    # HACK: remove after gerrit 481121
    __import__('atexit').unregister(pywikibot.comms.http._flush)

    # HACK: Why is pywikibot revision object so limited?
    orig_update_revisions = pywikibot.data.api._update_revisions

    def _update_revisions(page, revisions):
        orig_update_revisions(page, revisions)
        for rev in revisions:
            page._revisions[rev['revid']].apidata = rev

    pywikibot.data.api._update_revisions = _update_revisions

    # HACK: Why does Pywikibot have to do so much processing with API results
    def getRedirectTargetRAW(self):
        title = self.title(with_section=False)
        query = self.site._simple_request(
            action='query',
            prop='info',
            titles=title,
            redirects=True)
        result = query.submit()

        # Normalize title
        for item in result['query'].get('normalized', []):
            if item['from'] == title:
                title = item['to']
                break

        for item in result['query']['redirects']:
            if item['from'] == title:
                # Ignore fragments
                return item['to']

        raise RuntimeError

    pywikibot.Page.getRedirectTargetRAW = getRedirectTargetRAW

do_pywikibot_patches()


def hex_to_base36(value):
    value = int(value, 16)
    chars = '0123456789abcdefghijklmnopqrstuvwxyz'
    result = ''
    while value:
        value, remainder = divmod(value, 36)
        result = chars[remainder] + result
    return result


class XMLWriter(object):
    def __init__(self, file):
        self.f = file
        self.level = 0

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.f.close()

    def _fixup_attrib_order(self, string, attrib):
        if len(attrib) < 2 or not isinstance(attrib, OrderedDict):
            return string
        opener = re.match(r'^<[^>]+', string).group(0)
        attrib_xml = {
            key: re.search(
                re.escape(escape(key)) + r'="[^"]*"', opener).group(0)
            for key in attrib
        }

        old = ' '.join(attrib_xml[attr] for attr in sorted(attrib))
        assert old in opener
        new = ' '.join(attrib_xml[attr] for attr in attrib)

        new_opener = opener.replace(old, new, 1)
        assert len(opener) == len(new_opener)

        return new_opener + string[len(new_opener):]

    def _attrib_ensure_str(self, attrib):
        for key, value in attrib.items():
            attrib[key] = str(value)

    def textnode(self, tag, value, attrib={}):
        self.f.write('  ' * self.level)
        self._attrib_ensure_str(attrib)
        element = etree.Element(tag, attrib=attrib)
        element.text = value is not None and str(value)
        self.f.write(self._fixup_attrib_order(
            etree.tostring(element, encoding='unicode'), attrib))
        self.f.write('\n')

    @contextmanager
    def containernode(self, tag, attrib={}):
        element = etree.Element(tag, attrib=attrib)
        emptytag = etree.tostring(element, encoding='unicode',
                                  short_empty_elements=False)
        opener, closer = emptytag.split('></')
        opener, closer = opener + '>', '</' + closer

        opener = self._fixup_attrib_order(opener, attrib)

        self.f.write('  ' * self.level + opener + '\n')
        self.level += 1

        yield

        self.level -= 1
        self.f.write('  ' * self.level + closer + '\n')


pywikibot.config.family_files['comarc'] = (
    'https://commonsarchive.wmflabs.org/w/api.php')
site = pywikibot.Site('comarc', 'comarc')

with XMLWriter(sys.stdout) as w:
    with w.containernode('mediawiki', OrderedDict([
        ('xmlns', 'http://www.mediawiki.org/xml/export-0.10/'),
        ('xmlns:xsi', 'http://www.w3.org/2001/XMLSchema-instance'),
        ('xsi:schemaLocation', 'http://www.mediawiki.org/xml/export-0.10/ '
                               'http://www.mediawiki.org/xml/export-0.10.xsd'),
        ('version', '0.10'),
        ('xml:lang', 'en'),
    ])):
        with w.containernode('siteinfo'):
            siteinfo = site.siteinfo
            w.textnode('sitename', siteinfo['sitename'])
            w.textnode('dbname', siteinfo['wikiid'])
            w.textnode('base', siteinfo['base'])
            w.textnode('generator', siteinfo['generator'])
            w.textnode('case', siteinfo['case'])

            with w.containernode('namespaces'):
                for key, ns in sorted(site.namespaces.items()):
                    w.textnode('namespace', ns.custom_name, OrderedDict([
                        ('key', ns.id),
                        ('case', ns.case),
                    ]))

        for id in site.namespaces:
            if id < 0:
                continue
            pages = site.allpages(namespace=id)
            for page in pages:
                try:
                    page.latest_file_info
                except (AttributeError, pywikibot.PageRelatedError):
                    pass
                else:
                    page.download()
                with w.containernode('page'):
                    w.textnode('title', page.title())
                    w.textnode('ns', page.namespace().id)
                    w.textnode('id', page.pageid)

                    if page.isRedirectPage():
                        w.textnode('redirect', None, {
                            'title': page.getRedirectTargetRAW()
                        })

                    protection = ':'.join('{}={}'.format(key, value)
                                          for key, value in page.protection())

                    if protection:
                        w.textnode('restrictions', protection)

                    for revision in page.revisions(reverse=True, content=True):
                        with w.containernode('revision'):
                            w.textnode('id', revision.revid)

                            parentid = int(revision.parent_id)
                            if parentid:
                                w.textnode('parentid', parentid)

                            w.textnode(
                                'timestamp',
                                revision.timestamp.isoformat())

                            if 'userhidden' in revision.apidata:
                                w.textnode('contributor', None, {
                                    'deleted': 'deleted'
                                })
                            else:
                                with w.containernode('contributor'):
                                    contributor = pywikibot.User(
                                        site,
                                        revision.user)
                                    if not contributor.isAnonymous():
                                        w.textnode('username', revision.user)
                                        w.textnode(
                                            'id',
                                            contributor.getprops()['userid']
                                            if contributor.isRegistered()
                                            else 0)
                                    else:
                                        w.textnode('ip', revision.user)

                            if revision.minor:
                                w.textnode('minor', None)

                            if 'commenthidden' in revision.apidata:
                                w.textnode('comment', None, {
                                    'deleted': 'deleted'
                                })
                            elif revision.comment:
                                w.textnode('comment', revision.comment)

                            w.textnode('model', revision.content_model)

                            w.textnode('format',
                                       revision.apidata['contentformat'])

                            if 'texthidden' in revision.apidata:
                                w.textnone('text', None, {
                                    'deleted': 'deleted'
                                })
                            else:
                                w.textnode('text', revision.text, {
                                    'xml:space': 'preserve'
                                })

                            w.textnode('sha1',
                                       hex_to_base36(revision.sha1).zfill(31))

from errbot import BotPlugin
import logging
import re
import requests
from requests_kerberos import HTTPKerberosAuth, DISABLED
from itertools import chain

CONFIG_TEMPLATE = {'URL': "http://jira.example.com",
                   'PROJECTS': ['FOO', 'BAR'],
                   'KERBEROS': True,
                   'USERNAME': 'foo',
                   'PASSWORD': 'bar'
                  }

class Jira(BotPlugin):
    """A plugin for interacting with Atlassian JIRA"""
    min_err_version = '1.6.0'  # Optional, but recommended
    max_err_version = '2.0.0'  # Optional, but recommended

    def get_configuration_template(self):
        """Defines the configuration structure this plugin supports"""
        return CONFIG_TEMPLATE

    def configure(self, configuration):
        """
        Creates a Python dictionary object which contains all the values from our
        CONFIG_TEMPLATE and then updates that dictionary with the configuration
        received when calling the "!plugin config JIRA" command.
        """

        if configuration is not None and configuration != {}:
            config = dict(chain(CONFIG_TEMPLATE.items(),
                                configuration.items()))
        else:
            config = CONFIG_TEMPLATE
        super(Jira, self).configure(config)


    def get_cookie(self):
        r = requests.get(self.config['URL']+'/step-auth-gss',
                         auth=HTTPKerberosAuth(mutual_authentication=DISABLED),
                         verify=False)
        return r.cookies['JSESSIONID']

    def get_issue(self, issue_id):
        """Retrieves issue JSON from JIRA"""
        try:
            cookie = self.get_cookie()
            logging.info("[JIRA] got cookie %s" % cookie)
        except:
            cookie = ''
        response = requests.get(
            self.config['URL']+'/rest/api/latest/issue/'+issue_id+'.json',
            headers={"Cookie": "JSESSIONID=%s" % cookie}, verify=False)
        logging.info("[JIRA] got response %s" % response.status_code)
        return response

    def get_response_text(self, mess):
        if self.config:
            matches = []
            regexes = []
            for project in self.config['PROJECTS']:
                regexes.append(r'(%s\-[0-9]+)' % project)
            for regex in regexes:
                matches.extend(re.findall(regex, mess.body, flags=re.IGNORECASE))
            if matches:
                # set() gives us uniques, but does not preserve order.
                for match in set(matches):
                    issue_id = match
                    logging.info("[JIRA] matched issue_id: %s" % issue_id)
                    issue_response = self.get_issue(issue_id)
                    if issue_response.status_code in (200,):
                        logging.info("[JIRA] retrieved issue data: %s" % issue_response)
                        issue_summary = issue_response.json()['fields']['summary']
                        return "%s/browse/%s - %s" % (self.config['URL'], issue_id, issue_summary)
                    elif issue_response.status_code in (401,):
                        logging.error("[JIRA] Access Denied")
                    elif issue_response.status_code in (404,):
                        return "Issue not found"
                    else:
                        logging.error("[JIRA] encountered unknown response status code: %s" % issue_response.status_code)
                        logging.error("[JIRA] response body: %s" % issue_response.json())

    def callback_message(self, mess):
        """A callback which responds to mention of JIRA issues"""
        text_message = self.get_response_text(mess)
        if not text_message:
            return

        if mess.is_direct:
            self.send(mess.frm, text_message)
        elif mess.is_group:
            self.send(mess.frm.room, text_message)

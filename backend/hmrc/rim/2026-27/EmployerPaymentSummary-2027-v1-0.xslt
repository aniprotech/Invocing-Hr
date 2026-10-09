<?xml version="1.0" encoding="UTF-8"?>
<axsl:stylesheet xmlns:axsl="http://www.w3.org/1999/XSL/Transform" xmlns:dsig="http://www.w3.org/2000/09/xmldsig#" xmlns:eps="http://www.govtalk.gov.uk/taxation/PAYE/RTI/EmployerPaymentSummary/26-27/1" xmlns:hd="http://www.govtalk.gov.uk/CM/envelope" xmlns:date="http://exslt.org/dates-and-times" xmlns:dyn="http://exslt.org/dynamic" xmlns:exsl="http://exslt.org/common" xmlns:iso="http://purl.oclc.org/dsdl/schematron" xmlns:math="http://exslt.org/math" xmlns:random="http://exslt.org/random" xmlns:regexp="http://exslt.org/regular-expressions" xmlns:sch="http://www.ascc.net/xml/schematron" xmlns:set="http://exslt.org/sets" xmlns:str="http://exslt.org/strings" dsig:dummy-for-xmlns="" eps:dummy-for-xmlns="" exclude-result-prefixes="sch iso" extension-element-prefixes="date dyn math random regexp set str exsl" hd:dummy-for-xmlns="" version="1.0">

<!--PHASES-->


<!--PROLOG-->
<dsl-rim:namespaceMappings xmlns:dsl-rim="http://www.decisionsoft.com/rim" xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse">
    <dsl-rim:namespaceMapping prefix="hd" uri="http://www.govtalk.gov.uk/CM/envelope"/>
    <dsl-rim:namespaceMapping prefix="dsig" uri="http://www.w3.org/2000/09/xmldsig#"/>
    <dsl-rim:namespaceMapping prefix="eps" uri="http://www.govtalk.gov.uk/taxation/PAYE/RTI/EmployerPaymentSummary/26-27/1"/>
  </dsl-rim:namespaceMappings>
  <axsl:output xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" indent="yes" method="xml" omit-xml-declaration="no" standalone="yes"/>

<!--KEYS-->


<!--DEFAULT RULES-->


<!--MODE: SCHEMATRON-FULL-PATH-->
<axsl:template match="*" mode="schematron-get-full-path">
    <axsl:apply-templates mode="schematron-get-full-path" select="parent::*"/>
    <axsl:text>/</axsl:text>
    <axsl:variable name="nsuri" select="namespace-uri()"/>
    <axsl:variable xmlns:dsl-rim="http://www.decisionsoft.com/rim" name="prefix" select="document('')//dsl-rim:namespaceMapping[@uri=$nsuri]/@prefix"/>
    <axsl:if test="$prefix">
      <axsl:value-of select="concat($prefix,':')"/>
    </axsl:if>
    <axsl:value-of select="local-name()"/>
    <axsl:variable name="preceding" select="count(preceding-sibling::*[local-name()=local-name(current())                                   and namespace-uri() = namespace-uri(current())])"/>
    <axsl:text>[</axsl:text>
    <axsl:value-of select="1+ $preceding"/>
    <axsl:text>]</axsl:text>
  </axsl:template>
  <axsl:template match="@*" mode="schematron-get-full-path">
    <axsl:apply-templates mode="schematron-get-full-path" select="parent::*"/>
    <axsl:text>/@</axsl:text>
    <axsl:variable name="nsuri" select="namespace-uri()"/>
    <axsl:variable xmlns:dsl-rim="http://www.decisionsoft.com/rim" name="prefix" select="document('')//dsl-rim:namespaceMapping[@uri=$nsuri]/@prefix"/>
    <axsl:if test="$prefix">
      <axsl:value-of select="concat($prefix,':')"/>
    </axsl:if>
    <axsl:value-of select="local-name()"/>
  </axsl:template>
  <!--Strip characters-->
  <axsl:template match="text()" priority="-1"/>

<!--SCHEMA METADATA-->
<axsl:template match="/">
    <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="errors">
      <axsl:apply-templates mode="M4" select="/"/>
      <axsl:apply-templates mode="M5" select="/"/>
      <axsl:apply-templates mode="M6" select="/"/>
      <axsl:apply-templates mode="M7" select="/"/>
      <axsl:apply-templates mode="M8" select="/"/>
      <axsl:apply-templates mode="M9" select="/"/>
      <axsl:apply-templates mode="M10" select="/"/>
      <axsl:apply-templates mode="M11" select="/"/>
      <axsl:apply-templates mode="M12" select="/"/>
      <axsl:apply-templates mode="M13" select="/"/>
      <axsl:apply-templates mode="M14" select="/"/>
      <axsl:apply-templates mode="M15" select="/"/>
      <axsl:apply-templates mode="M16" select="/"/>
      <axsl:apply-templates mode="M17" select="/"/>
      <axsl:apply-templates mode="M18" select="/"/>
      <axsl:apply-templates mode="M19" select="/"/>
      <axsl:apply-templates mode="M20" select="/"/>
      <axsl:apply-templates mode="M21" select="/"/>
    </axsl:variable>
    <err:ErrorResponse xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" xmlns:dsl="http://decisionsoft.com/rim/errorExtension" SchemaVersion="2.0">
      <axsl:copy-of select="$errors"/>
    </err:ErrorResponse>
  </axsl:template>

<!--SCHEMATRON PATTERNS-->


<!--PATTERN p39-->


	<!--RULE -->
<axsl:template match="/hd:GovTalkMessage/hd:Body/eps:IRenvelope/eps:IRheader/eps:Keys/eps:Key" mode="M4" priority="4000">

		<!--ASSERT -->
<axsl:choose>
      <axsl:when test="count(../../../../../hd:GovTalkDetails/hd:Keys/hd:Key[@Type = current()/@Type and . = current()]) &gt; 0"/>
      <axsl:otherwise>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="errorCode">5005</axsl:variable>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="defaultMessage">Keys in the GovTalkDetails do not match those in the IRheader.</axsl:variable>
        <err:Error xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" xmlns:dsl="http://decisionsoft.com/rim/errorExtension">
          <err:RaisedBy>ChRIS</err:RaisedBy>
          <err:Number>
            <axsl:value-of select="normalize-space($errorCode)"/>
          </err:Number>
          <err:Type>business</err:Type>
          <err:Text>
            <axsl:choose>
              <axsl:when test="normalize-space($defaultMessage)">
                <axsl:copy-of select="$defaultMessage"/>
              </axsl:when>
              <axsl:otherwise>Keys in the IR header must also exist in the GovTalk header with the same value</axsl:otherwise>
            </axsl:choose>
          </err:Text>
          <err:Location>
            <axsl:apply-templates mode="schematron-get-full-path" select="."/>
          </err:Location>
        </err:Error>
      </axsl:otherwise>
    </axsl:choose>
    <axsl:apply-templates mode="M4" select="@*|*|comment()|processing-instruction()"/>
  </axsl:template>
  <axsl:template match="text()" mode="M4" priority="-1"/>
  <axsl:template match="@*|node()" mode="M4" priority="-2">
    <axsl:apply-templates mode="M4" select="@*|node()"/>
  </axsl:template>

<!--PATTERN p38-->


	<!--RULE -->
<axsl:template match="/hd:GovTalkMessage/hd:Body/eps:IRenvelope/eps:IRheader" mode="M5" priority="4000">

		<!--ASSERT -->
<axsl:choose>
      <axsl:when test="count(eps:Keys/eps:Key) &gt; 0"/>
      <axsl:otherwise>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="errorCode">5004</axsl:variable>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="defaultMessage">At least one key must exist in the IRheader</axsl:variable>
        <err:Error xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" xmlns:dsl="http://decisionsoft.com/rim/errorExtension">
          <err:RaisedBy>ChRIS</err:RaisedBy>
          <err:Number>
            <axsl:value-of select="normalize-space($errorCode)"/>
          </err:Number>
          <err:Type>business</err:Type>
          <err:Text>
            <axsl:choose>
              <axsl:when test="normalize-space($defaultMessage)">
                <axsl:copy-of select="$defaultMessage"/>
              </axsl:when>
              <axsl:otherwise>At least one key must exist in the IRheader</axsl:otherwise>
            </axsl:choose>
          </err:Text>
          <err:Location>
            <axsl:apply-templates mode="schematron-get-full-path" select="."/>
          </err:Location>
        </err:Error>
      </axsl:otherwise>
    </axsl:choose>
    <axsl:apply-templates mode="M5" select="@*|*|comment()|processing-instruction()"/>
  </axsl:template>
  <axsl:template match="text()" mode="M5" priority="-1"/>
  <axsl:template match="@*|node()" mode="M5" priority="-2">
    <axsl:apply-templates mode="M5" select="@*|node()"/>
  </axsl:template>

<!--PATTERN p41-->


	<!--RULE -->
<axsl:template match="/hd:GovTalkMessage/hd:Body/eps:IRenvelope/eps:EmployerPaymentSummary/eps:EmpRefs/eps:OfficeNo" mode="M6" priority="4000">

		<!--ASSERT -->
<axsl:choose>
      <axsl:when test="../../../eps:IRheader/eps:Keys/eps:Key[@Type = 'TaxOfficeNumber'] = ."/>
      <axsl:otherwise>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="errorCode">7821</axsl:variable>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="defaultMessage">The TaxOfficeNumber key within the IRheader must match [HMRCOFFICENUMBER]</axsl:variable>
        <err:Error xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" xmlns:dsl="http://decisionsoft.com/rim/errorExtension">
          <err:RaisedBy>ChRIS</err:RaisedBy>
          <err:Number>
            <axsl:value-of select="normalize-space($errorCode)"/>
          </err:Number>
          <err:Type>business</err:Type>
          <err:Text>
            <axsl:choose>
              <axsl:when test="normalize-space($defaultMessage)">
                <axsl:copy-of select="$defaultMessage"/>
              </axsl:when>
              <axsl:otherwise>The TaxOfficeNumber key within the IRheader must match [HMRCOFFICENUMBER]</axsl:otherwise>
            </axsl:choose>
          </err:Text>
          <err:Location>
            <axsl:apply-templates mode="schematron-get-full-path" select="."/>
          </err:Location>
        </err:Error>
      </axsl:otherwise>
    </axsl:choose>
    <axsl:apply-templates mode="M6" select="@*|*|comment()|processing-instruction()"/>
  </axsl:template>
  <axsl:template match="text()" mode="M6" priority="-1"/>
  <axsl:template match="@*|node()" mode="M6" priority="-2">
    <axsl:apply-templates mode="M6" select="@*|node()"/>
  </axsl:template>

<!--PATTERN p42-->


	<!--RULE -->
<axsl:template match="/hd:GovTalkMessage/hd:Body/eps:IRenvelope/eps:EmployerPaymentSummary/eps:EmpRefs/eps:PayeRef" mode="M7" priority="4000">

		<!--ASSERT -->
<axsl:choose>
      <axsl:when test="../../../eps:IRheader/eps:Keys/eps:Key[@Type = 'TaxOfficeReference'] = ."/>
      <axsl:otherwise>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="errorCode">7822</axsl:variable>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="defaultMessage">The TaxOfficeReference key within the IRheader must match [EMPLOYERPAYEREF]</axsl:variable>
        <err:Error xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" xmlns:dsl="http://decisionsoft.com/rim/errorExtension">
          <err:RaisedBy>ChRIS</err:RaisedBy>
          <err:Number>
            <axsl:value-of select="normalize-space($errorCode)"/>
          </err:Number>
          <err:Type>business</err:Type>
          <err:Text>
            <axsl:choose>
              <axsl:when test="normalize-space($defaultMessage)">
                <axsl:copy-of select="$defaultMessage"/>
              </axsl:when>
              <axsl:otherwise>The TaxOfficeReference key within the IRheader must match [EMPLOYERPAYEREF]</axsl:otherwise>
            </axsl:choose>
          </err:Text>
          <err:Location>
            <axsl:apply-templates mode="schematron-get-full-path" select="."/>
          </err:Location>
        </err:Error>
      </axsl:otherwise>
    </axsl:choose>
    <axsl:apply-templates mode="M7" select="@*|*|comment()|processing-instruction()"/>
  </axsl:template>
  <axsl:template match="text()" mode="M7" priority="-1"/>
  <axsl:template match="@*|node()" mode="M7" priority="-2">
    <axsl:apply-templates mode="M7" select="@*|node()"/>
  </axsl:template>

<!--PATTERN p43-->


	<!--RULE -->
<axsl:template match="/hd:GovTalkMessage/hd:Body/eps:IRenvelope/eps:EmployerPaymentSummary/eps:EmpRefs/eps:COTAXRef" mode="M8" priority="4000">

		<!--ASSERT -->
<axsl:choose>
      <axsl:when test="(((11 - (((6 * substring(., 2, 1)) + (7 * substring(., 3, 1)) + (8 * substring(., 4, 1)) + (9 * substring(., 5, 1)) + (10 * substring(., 6, 1)) + (5 * substring(., 7, 1)) + (4 * substring(., 8, 1)) + (3 * substring(., 9, 1)) + (2 * substring(., 10, 1))) mod 11)) &gt; 9) and (substring(., 1, 1) = (11 - (((6 * substring(., 2, 1)) + (7 * substring(., 3, 1)) + (8 * substring(., 4, 1)) + (9 * substring(., 5, 1)) + (10 * substring(., 6, 1)) + (5 * substring(., 7, 1)) + (4 * substring(., 8, 1)) + (3 * substring(., 9, 1)) + (2 * substring(., 10, 1))) mod 11)) - 9))                 or                 (substring(., 1, 1) = (11 - (((6 * substring(., 2, 1)) + (7 * substring(., 3, 1)) + (8 * substring(., 4, 1)) + (9 * substring(., 5, 1)) + (10 * substring(., 6, 1)) + (5 * substring(., 7, 1)) + (4 * substring(., 8, 1)) + (3 * substring(., 9, 1)) + (2 * substring(., 10, 1))) mod 11)))"/>
      <axsl:otherwise>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="errorCode">7882</axsl:variable>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="defaultMessage">The entry must be a valid UTR. Please check.</axsl:variable>
        <err:Error xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" xmlns:dsl="http://decisionsoft.com/rim/errorExtension">
          <err:RaisedBy>ChRIS</err:RaisedBy>
          <err:Number>
            <axsl:value-of select="normalize-space($errorCode)"/>
          </err:Number>
          <err:Type>business</err:Type>
          <err:Text>
            <axsl:choose>
              <axsl:when test="normalize-space($defaultMessage)">
                <axsl:copy-of select="$defaultMessage"/>
              </axsl:when>
              <axsl:otherwise>Must be valid against the UTR algorithm</axsl:otherwise>
            </axsl:choose>
          </err:Text>
          <err:Location>
            <axsl:apply-templates mode="schematron-get-full-path" select="."/>
          </err:Location>
        </err:Error>
      </axsl:otherwise>
    </axsl:choose>
    <axsl:apply-templates mode="M8" select="@*|*|comment()|processing-instruction()"/>
  </axsl:template>
  <axsl:template match="text()" mode="M8" priority="-1"/>
  <axsl:template match="@*|node()" mode="M8" priority="-2">
    <axsl:apply-templates mode="M8" select="@*|node()"/>
  </axsl:template>

<!--PATTERN p44-->


	<!--RULE -->
<axsl:template match="/hd:GovTalkMessage/hd:Body/eps:IRenvelope/eps:EmployerPaymentSummary/eps:NoPaymentDates/eps:From" mode="M9" priority="4000">

		<!--ASSERT -->
<axsl:choose>
      <axsl:when test="(round(date:seconds(normalize-space(.)) div 86400) &lt;= round(date:seconds(normalize-space(date:date())) div 86400))"/>
      <axsl:otherwise>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="errorCode">7910</axsl:variable>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="defaultMessage">The entry in [NOPAYMENTDATEFROM] must be on or before today. Please check.</axsl:variable>
        <err:Error xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" xmlns:dsl="http://decisionsoft.com/rim/errorExtension">
          <err:RaisedBy>ChRIS</err:RaisedBy>
          <err:Number>
            <axsl:value-of select="normalize-space($errorCode)"/>
          </err:Number>
          <err:Type>business</err:Type>
          <err:Text>
            <axsl:choose>
              <axsl:when test="normalize-space($defaultMessage)">
                <axsl:copy-of select="$defaultMessage"/>
              </axsl:when>
              <axsl:otherwise>[NOPAYMENTDATEFROM] must be on or before the current date.</axsl:otherwise>
            </axsl:choose>
          </err:Text>
          <err:Location>
            <axsl:apply-templates mode="schematron-get-full-path" select="."/>
          </err:Location>
        </err:Error>
      </axsl:otherwise>
    </axsl:choose>

		<!--ASSERT -->
<axsl:choose>
      <axsl:when test="(round(date:seconds(normalize-space(.)) div 86400) &lt; round(date:seconds(normalize-space(../eps:To)) div 86400))"/>
      <axsl:otherwise>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="errorCode">7869</axsl:variable>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="defaultMessage">[NOPAYMENTDATEFROM] must be before [NOPAYMENTDATETO]. Please check.</axsl:variable>
        <err:Error xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" xmlns:dsl="http://decisionsoft.com/rim/errorExtension">
          <err:RaisedBy>ChRIS</err:RaisedBy>
          <err:Number>
            <axsl:value-of select="normalize-space($errorCode)"/>
          </err:Number>
          <err:Type>business</err:Type>
          <err:Text>
            <axsl:choose>
              <axsl:when test="normalize-space($defaultMessage)">
                <axsl:copy-of select="$defaultMessage"/>
              </axsl:when>
              <axsl:otherwise>[NOPAYMENTDATEFROM] must be before [NOPAYMENTDATETO]</axsl:otherwise>
            </axsl:choose>
          </err:Text>
          <err:Location>
            <axsl:apply-templates mode="schematron-get-full-path" select="."/>
          </err:Location>
        </err:Error>
      </axsl:otherwise>
    </axsl:choose>
    <axsl:apply-templates mode="M9" select="@*|*|comment()|processing-instruction()"/>
  </axsl:template>
  <axsl:template match="text()" mode="M9" priority="-1"/>
  <axsl:template match="@*|node()" mode="M9" priority="-2">
    <axsl:apply-templates mode="M9" select="@*|node()"/>
  </axsl:template>

<!--PATTERN p45-->


	<!--RULE -->
<axsl:template match="/hd:GovTalkMessage/hd:Body/eps:IRenvelope/eps:EmployerPaymentSummary/eps:NoPaymentDates/eps:To" mode="M10" priority="4000">

		<!--ASSERT -->
<axsl:choose>
      <axsl:when test="(round(date:seconds(normalize-space(date:add(normalize-space(.),normalize-space(&quot;-P1M&quot;)))) div 86400) &lt; round(date:seconds(normalize-space(date:date())) div 86400))"/>
      <axsl:otherwise>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="errorCode">7911</axsl:variable>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="defaultMessage">The entry in [NOPAYMENTDATETO] must be no later than the 5th of the current tax month. Please check.</axsl:variable>
        <err:Error xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" xmlns:dsl="http://decisionsoft.com/rim/errorExtension">
          <err:RaisedBy>ChRIS</err:RaisedBy>
          <err:Number>
            <axsl:value-of select="normalize-space($errorCode)"/>
          </err:Number>
          <err:Type>business</err:Type>
          <err:Text>
            <axsl:choose>
              <axsl:when test="normalize-space($defaultMessage)">
                <axsl:copy-of select="$defaultMessage"/>
              </axsl:when>
              <axsl:otherwise>[NOPAYMENTDATETO] must be no later than the end of the current tax month - the 5th.</axsl:otherwise>
            </axsl:choose>
          </err:Text>
          <err:Location>
            <axsl:apply-templates mode="schematron-get-full-path" select="."/>
          </err:Location>
        </err:Error>
      </axsl:otherwise>
    </axsl:choose>
    <axsl:apply-templates mode="M10" select="@*|*|comment()|processing-instruction()"/>
  </axsl:template>
  <axsl:template match="text()" mode="M10" priority="-1"/>
  <axsl:template match="@*|node()" mode="M10" priority="-2">
    <axsl:apply-templates mode="M10" select="@*|node()"/>
  </axsl:template>

<!--PATTERN p47-->


	<!--RULE -->
<axsl:template match="/hd:GovTalkMessage/hd:Body/eps:IRenvelope/eps:EmployerPaymentSummary/eps:PeriodOfInactivity/eps:From" mode="M11" priority="4000">

		<!--ASSERT -->
<axsl:choose>
      <axsl:when test="(round(date:seconds(normalize-space(.)) div 86400) &lt; round(date:seconds(normalize-space(../eps:To)) div 86400))"/>
      <axsl:otherwise>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="errorCode">7872</axsl:variable>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="defaultMessage">[PERIODOFINACTIVITYFROM] must be before [PERIODOFINACTIVITYTO]. Please check</axsl:variable>
        <err:Error xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" xmlns:dsl="http://decisionsoft.com/rim/errorExtension">
          <err:RaisedBy>ChRIS</err:RaisedBy>
          <err:Number>
            <axsl:value-of select="normalize-space($errorCode)"/>
          </err:Number>
          <err:Type>business</err:Type>
          <err:Text>
            <axsl:choose>
              <axsl:when test="normalize-space($defaultMessage)">
                <axsl:copy-of select="$defaultMessage"/>
              </axsl:when>
              <axsl:otherwise>[PERIODOFINACTIVITYFROM] must be before [PERIODOFINACTIVITYTO]</axsl:otherwise>
            </axsl:choose>
          </err:Text>
          <err:Location>
            <axsl:apply-templates mode="schematron-get-full-path" select="."/>
          </err:Location>
        </err:Error>
      </axsl:otherwise>
    </axsl:choose>

		<!--ASSERT -->
<axsl:choose>
      <axsl:when test="(                ( (round(date:seconds(normalize-space(date:date())) div 86400) &lt;= round(date:seconds(normalize-space(concat(date:year(), '-12-05'))) div 86400))                   and                 date:year(normalize-space((.))) = date:year()               )                 or               (                 not ( (round(date:seconds(normalize-space(date:date())) div 86400) &lt;= round(date:seconds(normalize-space(concat(date:year(), '-12-05'))) div 86400)) )                      and                    date:year(normalize-space((.))) = (date:year() + 1)               )             )              and              date:month-in-year(normalize-space(.)) = (date:month-in-year(normalize-space(date:add(normalize-space(date:date()),normalize-space('-P5D')))) mod 12) + 1"/>
      <axsl:otherwise>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="errorCode">7873</axsl:variable>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="defaultMessage">[PERIODOFINACTIVITYFROM] must be the start of the next tax month. Please check</axsl:variable>
        <err:Error xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" xmlns:dsl="http://decisionsoft.com/rim/errorExtension">
          <err:RaisedBy>ChRIS</err:RaisedBy>
          <err:Number>
            <axsl:value-of select="normalize-space($errorCode)"/>
          </err:Number>
          <err:Type>business</err:Type>
          <err:Text>
            <axsl:choose>
              <axsl:when test="normalize-space($defaultMessage)">
                <axsl:copy-of select="$defaultMessage"/>
              </axsl:when>
              <axsl:otherwise>[PERIODOFINACTIVITYFROM] must be the start of the next tax month</axsl:otherwise>
            </axsl:choose>
          </err:Text>
          <err:Location>
            <axsl:apply-templates mode="schematron-get-full-path" select="."/>
          </err:Location>
        </err:Error>
      </axsl:otherwise>
    </axsl:choose>
    <axsl:apply-templates mode="M11" select="@*|*|comment()|processing-instruction()"/>
  </axsl:template>
  <axsl:template match="text()" mode="M11" priority="-1"/>
  <axsl:template match="@*|node()" mode="M11" priority="-2">
    <axsl:apply-templates mode="M11" select="@*|node()"/>
  </axsl:template>

<!--PATTERN p48-->


	<!--RULE -->
<axsl:template match="/hd:GovTalkMessage/hd:Body/eps:IRenvelope/eps:EmployerPaymentSummary/eps:PeriodOfInactivity/eps:To" mode="M12" priority="4000">

		<!--ASSERT -->
<axsl:choose>
      <axsl:when test="(round(date:seconds(normalize-space(date:date())) div 86400) &lt; round(date:seconds(normalize-space(.)) div 86400))"/>
      <axsl:otherwise>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="errorCode">7874</axsl:variable>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="defaultMessage">[PERIODOFINACTIVITYTO] must be after today. Please check</axsl:variable>
        <err:Error xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" xmlns:dsl="http://decisionsoft.com/rim/errorExtension">
          <err:RaisedBy>ChRIS</err:RaisedBy>
          <err:Number>
            <axsl:value-of select="normalize-space($errorCode)"/>
          </err:Number>
          <err:Type>business</err:Type>
          <err:Text>
            <axsl:choose>
              <axsl:when test="normalize-space($defaultMessage)">
                <axsl:copy-of select="$defaultMessage"/>
              </axsl:when>
              <axsl:otherwise>[PERIODOFINACTIVITYTO] must be after the current date</axsl:otherwise>
            </axsl:choose>
          </err:Text>
          <err:Location>
            <axsl:apply-templates mode="schematron-get-full-path" select="."/>
          </err:Location>
        </err:Error>
      </axsl:otherwise>
    </axsl:choose>
    <axsl:apply-templates mode="M12" select="@*|*|comment()|processing-instruction()"/>
  </axsl:template>
  <axsl:template match="text()" mode="M12" priority="-1"/>
  <axsl:template match="@*|node()" mode="M12" priority="-2">
    <axsl:apply-templates mode="M12" select="@*|node()"/>
  </axsl:template>

<!--PATTERN p46-->


	<!--RULE -->
<axsl:template match="/hd:GovTalkMessage/hd:Body/eps:IRenvelope/eps:EmployerPaymentSummary/eps:PeriodOfInactivity" mode="M13" priority="4000">

		<!--ASSERT -->
<axsl:choose>
      <axsl:when test="(round(date:seconds(normalize-space(eps:To)) div 86400) &lt;= round(date:seconds(normalize-space(date:add(normalize-space(eps:From),normalize-space('P12M')))) div 86400))"/>
      <axsl:otherwise>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="errorCode">7871</axsl:variable>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="defaultMessage">[PERIODOFINACTIVITY] must be less than or equal to 12 months. Please check</axsl:variable>
        <err:Error xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" xmlns:dsl="http://decisionsoft.com/rim/errorExtension">
          <err:RaisedBy>ChRIS</err:RaisedBy>
          <err:Number>
            <axsl:value-of select="normalize-space($errorCode)"/>
          </err:Number>
          <err:Type>business</err:Type>
          <err:Text>
            <axsl:choose>
              <axsl:when test="normalize-space($defaultMessage)">
                <axsl:copy-of select="$defaultMessage"/>
              </axsl:when>
              <axsl:otherwise>[PERIODOFINACTIVITY] must be less than or equal to 12 months.</axsl:otherwise>
            </axsl:choose>
          </err:Text>
          <err:Location>
            <axsl:apply-templates mode="schematron-get-full-path" select="."/>
          </err:Location>
        </err:Error>
      </axsl:otherwise>
    </axsl:choose>
    <axsl:apply-templates mode="M13" select="@*|*|comment()|processing-instruction()"/>
  </axsl:template>
  <axsl:template match="text()" mode="M13" priority="-1"/>
  <axsl:template match="@*|node()" mode="M13" priority="-2">
    <axsl:apply-templates mode="M13" select="@*|node()"/>
  </axsl:template>

<!--PATTERN p50-->


	<!--RULE -->
<axsl:template match="/hd:GovTalkMessage/hd:Body/eps:IRenvelope/eps:EmployerPaymentSummary/eps:RecoverableAmountsYTD/eps:TaxMonth" mode="M14" priority="4000">

		<!--ASSERT -->
<axsl:choose>
      <axsl:when test="not('1' = (.))               or             (               (round(date:seconds(normalize-space(concat(2027 - 1, '-03-06'))) div 86400) &lt;= round(date:seconds(normalize-space(date:date())) div 86400))                 and               (round(date:seconds(normalize-space(date:date())) div 86400) &lt;= round(date:seconds(normalize-space(concat(2027 - 1, '-05-19'))) div 86400))             )"/>
      <axsl:otherwise>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="errorCode">7918</axsl:variable>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="defaultMessage">The entry in [TAXMONTH] of 1 is only valid if the submission is made between 6 March of the tax year before the [RELATEDTAXYEAR] and 19 May of the [RELATEDTAXYEAR] inclusive. Please check.</axsl:variable>
        <err:Error xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" xmlns:dsl="http://decisionsoft.com/rim/errorExtension">
          <err:RaisedBy>ChRIS</err:RaisedBy>
          <err:Number>
            <axsl:value-of select="normalize-space($errorCode)"/>
          </err:Number>
          <err:Type>business</err:Type>
          <err:Text>
            <axsl:choose>
              <axsl:when test="normalize-space($defaultMessage)">
                <axsl:copy-of select="$defaultMessage"/>
              </axsl:when>
              <axsl:otherwise>A [TAXMONTH] equal to 1 is only valid if the submission is made between 6 March of the tax year before [RELATEDTAXYEAR] and 19 May of [RELATEDTAXYEAR] inclusive.</axsl:otherwise>
            </axsl:choose>
          </err:Text>
          <err:Location>
            <axsl:apply-templates mode="schematron-get-full-path" select="."/>
          </err:Location>
        </err:Error>
      </axsl:otherwise>
    </axsl:choose>

		<!--ASSERT -->
<axsl:choose>
      <axsl:when test="not('2' = (.))               or             (               (round(date:seconds(normalize-space(concat(2027 - 1, '-04-06'))) div 86400) &lt;= round(date:seconds(normalize-space(date:date())) div 86400))                 and               (round(date:seconds(normalize-space(date:date())) div 86400) &lt;= round(date:seconds(normalize-space(concat(2027 - 1, '-06-19'))) div 86400))             )"/>
      <axsl:otherwise>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="errorCode">7919</axsl:variable>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="defaultMessage">The entry in [TAXMONTH] of 2 is only valid if the submission is made between 6 April and 19 June inclusive of the [RELATEDTAXYEAR]. Please check.</axsl:variable>
        <err:Error xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" xmlns:dsl="http://decisionsoft.com/rim/errorExtension">
          <err:RaisedBy>ChRIS</err:RaisedBy>
          <err:Number>
            <axsl:value-of select="normalize-space($errorCode)"/>
          </err:Number>
          <err:Type>business</err:Type>
          <err:Text>
            <axsl:choose>
              <axsl:when test="normalize-space($defaultMessage)">
                <axsl:copy-of select="$defaultMessage"/>
              </axsl:when>
              <axsl:otherwise>A [TAXMONTH] equal to 2 is only valid if the submission is made between 6 April and 19 June of [RELATEDTAXYEAR] inclusive.</axsl:otherwise>
            </axsl:choose>
          </err:Text>
          <err:Location>
            <axsl:apply-templates mode="schematron-get-full-path" select="."/>
          </err:Location>
        </err:Error>
      </axsl:otherwise>
    </axsl:choose>

		<!--ASSERT -->
<axsl:choose>
      <axsl:when test="not('3' = (.))               or             (               (round(date:seconds(normalize-space(concat(2027 - 1, '-05-06'))) div 86400) &lt;= round(date:seconds(normalize-space(date:date())) div 86400))                 and               (round(date:seconds(normalize-space(date:date())) div 86400) &lt;= round(date:seconds(normalize-space(concat(2027 - 1, '-07-19'))) div 86400))             )"/>
      <axsl:otherwise>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="errorCode">7920</axsl:variable>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="defaultMessage">The entry in [TAXMONTH] of 3 is only valid if the submission is made between 6 May and 19 July inclusive of the [RELATEDTAXYEAR]. Please check.</axsl:variable>
        <err:Error xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" xmlns:dsl="http://decisionsoft.com/rim/errorExtension">
          <err:RaisedBy>ChRIS</err:RaisedBy>
          <err:Number>
            <axsl:value-of select="normalize-space($errorCode)"/>
          </err:Number>
          <err:Type>business</err:Type>
          <err:Text>
            <axsl:choose>
              <axsl:when test="normalize-space($defaultMessage)">
                <axsl:copy-of select="$defaultMessage"/>
              </axsl:when>
              <axsl:otherwise>A [TAXMONTH] equal to 3 is only valid if the submission is made between 6 May and 19 July of [RELATEDTAXYEAR] inclusive.</axsl:otherwise>
            </axsl:choose>
          </err:Text>
          <err:Location>
            <axsl:apply-templates mode="schematron-get-full-path" select="."/>
          </err:Location>
        </err:Error>
      </axsl:otherwise>
    </axsl:choose>

		<!--ASSERT -->
<axsl:choose>
      <axsl:when test="not('4' = (.))               or             (               (round(date:seconds(normalize-space(concat(2027 - 1, '-06-06'))) div 86400) &lt;= round(date:seconds(normalize-space(date:date())) div 86400))                 and               (round(date:seconds(normalize-space(date:date())) div 86400) &lt;= round(date:seconds(normalize-space(concat(2027 - 1, '-08-19'))) div 86400))             )"/>
      <axsl:otherwise>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="errorCode">7921</axsl:variable>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="defaultMessage">The entry in [TAXMONTH] of 4 is only valid if the submission is made between 6 June and 19 August inclusive of the [RELATEDTAXYEAR]. Please check.</axsl:variable>
        <err:Error xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" xmlns:dsl="http://decisionsoft.com/rim/errorExtension">
          <err:RaisedBy>ChRIS</err:RaisedBy>
          <err:Number>
            <axsl:value-of select="normalize-space($errorCode)"/>
          </err:Number>
          <err:Type>business</err:Type>
          <err:Text>
            <axsl:choose>
              <axsl:when test="normalize-space($defaultMessage)">
                <axsl:copy-of select="$defaultMessage"/>
              </axsl:when>
              <axsl:otherwise>A [TAXMONTH] equal to 4 is only valid if the submission is made between 6 June and 19 August of [RELATEDTAXYEAR] inclusive.</axsl:otherwise>
            </axsl:choose>
          </err:Text>
          <err:Location>
            <axsl:apply-templates mode="schematron-get-full-path" select="."/>
          </err:Location>
        </err:Error>
      </axsl:otherwise>
    </axsl:choose>

		<!--ASSERT -->
<axsl:choose>
      <axsl:when test="not('5' = (.))               or             (               (round(date:seconds(normalize-space(concat(2027 - 1, '-07-06'))) div 86400) &lt;= round(date:seconds(normalize-space(date:date())) div 86400))                 and               (round(date:seconds(normalize-space(date:date())) div 86400) &lt;= round(date:seconds(normalize-space(concat(2027 - 1, '-09-19'))) div 86400))             )"/>
      <axsl:otherwise>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="errorCode">7922</axsl:variable>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="defaultMessage">The entry in [TAXMONTH] of 5 is only valid if the submission is made between 6 July and 19 September inclusive of the [RELATEDTAXYEAR]. Please check.</axsl:variable>
        <err:Error xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" xmlns:dsl="http://decisionsoft.com/rim/errorExtension">
          <err:RaisedBy>ChRIS</err:RaisedBy>
          <err:Number>
            <axsl:value-of select="normalize-space($errorCode)"/>
          </err:Number>
          <err:Type>business</err:Type>
          <err:Text>
            <axsl:choose>
              <axsl:when test="normalize-space($defaultMessage)">
                <axsl:copy-of select="$defaultMessage"/>
              </axsl:when>
              <axsl:otherwise>A [TAXMONTH] equal to 5 is only valid if the submission is made between 6 July and 19 September of [RELATEDTAXYEAR] inclusive.</axsl:otherwise>
            </axsl:choose>
          </err:Text>
          <err:Location>
            <axsl:apply-templates mode="schematron-get-full-path" select="."/>
          </err:Location>
        </err:Error>
      </axsl:otherwise>
    </axsl:choose>

		<!--ASSERT -->
<axsl:choose>
      <axsl:when test="not('6' = (.))               or             (               (round(date:seconds(normalize-space(concat(2027 - 1, '-08-06'))) div 86400) &lt;= round(date:seconds(normalize-space(date:date())) div 86400))                 and               (round(date:seconds(normalize-space(date:date())) div 86400) &lt;= round(date:seconds(normalize-space(concat(2027 - 1, '-10-19'))) div 86400))             )"/>
      <axsl:otherwise>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="errorCode">7923</axsl:variable>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="defaultMessage">The entry in [TAXMONTH] of 6 is only valid if the submission is made between 6 August and 19 October inclusive of the [RELATEDTAXYEAR]. Please check.</axsl:variable>
        <err:Error xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" xmlns:dsl="http://decisionsoft.com/rim/errorExtension">
          <err:RaisedBy>ChRIS</err:RaisedBy>
          <err:Number>
            <axsl:value-of select="normalize-space($errorCode)"/>
          </err:Number>
          <err:Type>business</err:Type>
          <err:Text>
            <axsl:choose>
              <axsl:when test="normalize-space($defaultMessage)">
                <axsl:copy-of select="$defaultMessage"/>
              </axsl:when>
              <axsl:otherwise>A [TAXMONTH] equal to 6 is only valid if the submission is made between 6 August and 19 October of [RELATEDTAXYEAR] inclusive.</axsl:otherwise>
            </axsl:choose>
          </err:Text>
          <err:Location>
            <axsl:apply-templates mode="schematron-get-full-path" select="."/>
          </err:Location>
        </err:Error>
      </axsl:otherwise>
    </axsl:choose>

		<!--ASSERT -->
<axsl:choose>
      <axsl:when test="not('7' = (.))               or             (               (round(date:seconds(normalize-space(concat(2027 - 1, '-09-06'))) div 86400) &lt;= round(date:seconds(normalize-space(date:date())) div 86400))                 and               (round(date:seconds(normalize-space(date:date())) div 86400) &lt;= round(date:seconds(normalize-space(concat(2027 - 1, '-11-19'))) div 86400))             )"/>
      <axsl:otherwise>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="errorCode">7924</axsl:variable>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="defaultMessage">The entry in [TAXMONTH] of 7 is only valid if the submission is made between 6 September and 19 November inclusive of the [RELATEDTAXYEAR]. Please check.</axsl:variable>
        <err:Error xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" xmlns:dsl="http://decisionsoft.com/rim/errorExtension">
          <err:RaisedBy>ChRIS</err:RaisedBy>
          <err:Number>
            <axsl:value-of select="normalize-space($errorCode)"/>
          </err:Number>
          <err:Type>business</err:Type>
          <err:Text>
            <axsl:choose>
              <axsl:when test="normalize-space($defaultMessage)">
                <axsl:copy-of select="$defaultMessage"/>
              </axsl:when>
              <axsl:otherwise>A [TAXMONTH] equal to 7 is only valid if the submission is made between 6 September and 19 November of [RELATEDTAXYEAR] inclusive.</axsl:otherwise>
            </axsl:choose>
          </err:Text>
          <err:Location>
            <axsl:apply-templates mode="schematron-get-full-path" select="."/>
          </err:Location>
        </err:Error>
      </axsl:otherwise>
    </axsl:choose>

		<!--ASSERT -->
<axsl:choose>
      <axsl:when test="not('8' = (.))               or             (               (round(date:seconds(normalize-space(concat(2027 - 1, '-10-06'))) div 86400) &lt;= round(date:seconds(normalize-space(date:date())) div 86400))                 and               (round(date:seconds(normalize-space(date:date())) div 86400) &lt;= round(date:seconds(normalize-space(concat(2027 - 1, '-12-19'))) div 86400))             )"/>
      <axsl:otherwise>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="errorCode">7925</axsl:variable>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="defaultMessage">The entry in [TAXMONTH] of 8 is only valid if the submission is made between 6 October and 19 December inclusive of the [RELATEDTAXYEAR]. Please check.</axsl:variable>
        <err:Error xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" xmlns:dsl="http://decisionsoft.com/rim/errorExtension">
          <err:RaisedBy>ChRIS</err:RaisedBy>
          <err:Number>
            <axsl:value-of select="normalize-space($errorCode)"/>
          </err:Number>
          <err:Type>business</err:Type>
          <err:Text>
            <axsl:choose>
              <axsl:when test="normalize-space($defaultMessage)">
                <axsl:copy-of select="$defaultMessage"/>
              </axsl:when>
              <axsl:otherwise>A [TAXMONTH] equal to 8 is only valid if the submission is made between 6 October and 19 December of [RELATEDTAXYEAR] inclusive.</axsl:otherwise>
            </axsl:choose>
          </err:Text>
          <err:Location>
            <axsl:apply-templates mode="schematron-get-full-path" select="."/>
          </err:Location>
        </err:Error>
      </axsl:otherwise>
    </axsl:choose>

		<!--ASSERT -->
<axsl:choose>
      <axsl:when test="not('9' = (.))               or             (               (round(date:seconds(normalize-space(concat(2027 - 1, '-11-06'))) div 86400) &lt;= round(date:seconds(normalize-space(date:date())) div 86400))                 and               (round(date:seconds(normalize-space(date:date())) div 86400) &lt;= round(date:seconds(normalize-space(concat(2027, '-01-19'))) div 86400))             )"/>
      <axsl:otherwise>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="errorCode">7926</axsl:variable>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="defaultMessage">The entry in [TAXMONTH] of 9 is only valid if the submission is made between 6 November and 19 January inclusive of the [RELATEDTAXYEAR]. Please check.</axsl:variable>
        <err:Error xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" xmlns:dsl="http://decisionsoft.com/rim/errorExtension">
          <err:RaisedBy>ChRIS</err:RaisedBy>
          <err:Number>
            <axsl:value-of select="normalize-space($errorCode)"/>
          </err:Number>
          <err:Type>business</err:Type>
          <err:Text>
            <axsl:choose>
              <axsl:when test="normalize-space($defaultMessage)">
                <axsl:copy-of select="$defaultMessage"/>
              </axsl:when>
              <axsl:otherwise>A [TAXMONTH] equal to 9 is only valid if the submission is made between 6 November and 19 January of [RELATEDTAXYEAR] inclusive.</axsl:otherwise>
            </axsl:choose>
          </err:Text>
          <err:Location>
            <axsl:apply-templates mode="schematron-get-full-path" select="."/>
          </err:Location>
        </err:Error>
      </axsl:otherwise>
    </axsl:choose>

		<!--ASSERT -->
<axsl:choose>
      <axsl:when test="not('10' = (.))               or             (               (round(date:seconds(normalize-space(concat(2027 - 1, '-12-06'))) div 86400) &lt;= round(date:seconds(normalize-space(date:date())) div 86400))                 and               (round(date:seconds(normalize-space(date:date())) div 86400) &lt;= round(date:seconds(normalize-space(concat(2027, '-02-19'))) div 86400))             )"/>
      <axsl:otherwise>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="errorCode">7927</axsl:variable>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="defaultMessage">The entry in [TAXMONTH] of 10 is only valid if the submission is made between 6 December and 19 February inclusive of the [RELATEDTAXYEAR]. Please check.</axsl:variable>
        <err:Error xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" xmlns:dsl="http://decisionsoft.com/rim/errorExtension">
          <err:RaisedBy>ChRIS</err:RaisedBy>
          <err:Number>
            <axsl:value-of select="normalize-space($errorCode)"/>
          </err:Number>
          <err:Type>business</err:Type>
          <err:Text>
            <axsl:choose>
              <axsl:when test="normalize-space($defaultMessage)">
                <axsl:copy-of select="$defaultMessage"/>
              </axsl:when>
              <axsl:otherwise>A [TAXMONTH] equal to 10 is only valid if the submission is made between 6 December and 19 February of [RELATEDTAXYEAR] inclusive.</axsl:otherwise>
            </axsl:choose>
          </err:Text>
          <err:Location>
            <axsl:apply-templates mode="schematron-get-full-path" select="."/>
          </err:Location>
        </err:Error>
      </axsl:otherwise>
    </axsl:choose>

		<!--ASSERT -->
<axsl:choose>
      <axsl:when test="not('11' = (.))               or             (               (round(date:seconds(normalize-space(concat(2027, '-01-06'))) div 86400) &lt;= round(date:seconds(normalize-space(date:date())) div 86400))                 and               (round(date:seconds(normalize-space(date:date())) div 86400) &lt;= round(date:seconds(normalize-space(concat(2027, '-03-19'))) div 86400))             )"/>
      <axsl:otherwise>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="errorCode">7928</axsl:variable>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="defaultMessage">The entry in [TAXMONTH] of 11 is only valid if the submission is made between 6 January and 19 March inclusive of the [RELATEDTAXYEAR]. Please check.</axsl:variable>
        <err:Error xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" xmlns:dsl="http://decisionsoft.com/rim/errorExtension">
          <err:RaisedBy>ChRIS</err:RaisedBy>
          <err:Number>
            <axsl:value-of select="normalize-space($errorCode)"/>
          </err:Number>
          <err:Type>business</err:Type>
          <err:Text>
            <axsl:choose>
              <axsl:when test="normalize-space($defaultMessage)">
                <axsl:copy-of select="$defaultMessage"/>
              </axsl:when>
              <axsl:otherwise>A [TAXMONTH] equal to 11 is only valid if the submission is made between 6 January and 19 March of [RELATEDTAXYEAR] inclusive.</axsl:otherwise>
            </axsl:choose>
          </err:Text>
          <err:Location>
            <axsl:apply-templates mode="schematron-get-full-path" select="."/>
          </err:Location>
        </err:Error>
      </axsl:otherwise>
    </axsl:choose>

		<!--ASSERT -->
<axsl:choose>
      <axsl:when test="not('12' = (.))               or             (round(date:seconds(normalize-space(concat(2027, '-02-06'))) div 86400) &lt;= round(date:seconds(normalize-space(date:date())) div 86400))"/>
      <axsl:otherwise>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="errorCode">7929</axsl:variable>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="defaultMessage">The entry in [TAXMONTH] of 12 is only valid if the submission is made on or after 6 February of the [RELATEDTAXYEAR]. Please check.</axsl:variable>
        <err:Error xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" xmlns:dsl="http://decisionsoft.com/rim/errorExtension">
          <err:RaisedBy>ChRIS</err:RaisedBy>
          <err:Number>
            <axsl:value-of select="normalize-space($errorCode)"/>
          </err:Number>
          <err:Type>business</err:Type>
          <err:Text>
            <axsl:choose>
              <axsl:when test="normalize-space($defaultMessage)">
                <axsl:copy-of select="$defaultMessage"/>
              </axsl:when>
              <axsl:otherwise>A [TAXMONTH] equal to 12 is only valid if the submission is made on or after 6 February of [RELATEDTAXYEAR].</axsl:otherwise>
            </axsl:choose>
          </err:Text>
          <err:Location>
            <axsl:apply-templates mode="schematron-get-full-path" select="."/>
          </err:Location>
        </err:Error>
      </axsl:otherwise>
    </axsl:choose>
    <axsl:apply-templates mode="M14" select="@*|*|comment()|processing-instruction()"/>
  </axsl:template>
  <axsl:template match="text()" mode="M14" priority="-1"/>
  <axsl:template match="@*|node()" mode="M14" priority="-2">
    <axsl:apply-templates mode="M14" select="@*|node()"/>
  </axsl:template>

<!--PATTERN p51-->


	<!--RULE -->
<axsl:template match="/hd:GovTalkMessage/hd:Body/eps:IRenvelope/eps:EmployerPaymentSummary/eps:RecoverableAmountsYTD/eps:CISDeductionsSuffered" mode="M15" priority="4000">

		<!--ASSERT -->
<axsl:choose>
      <axsl:when test="(((.)) - (0) &lt; 0.001) or ../../eps:EmpRefs/eps:COTAXRef"/>
      <axsl:otherwise>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="errorCode">7953</axsl:variable>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="defaultMessage">If [CISDEDUCTIONSSUFFERED] is greater than zero, [COTAXREF] must be present</axsl:variable>
        <err:Error xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" xmlns:dsl="http://decisionsoft.com/rim/errorExtension">
          <err:RaisedBy>ChRIS</err:RaisedBy>
          <err:Number>
            <axsl:value-of select="normalize-space($errorCode)"/>
          </err:Number>
          <err:Type>business</err:Type>
          <err:Text>
            <axsl:choose>
              <axsl:when test="normalize-space($defaultMessage)">
                <axsl:copy-of select="$defaultMessage"/>
              </axsl:when>
              <axsl:otherwise>If [CISDEDUCTIONSSUFFERED] is greater than zero, [COTAXREF] must be present</axsl:otherwise>
            </axsl:choose>
          </err:Text>
          <err:Location>
            <axsl:apply-templates mode="schematron-get-full-path" select="."/>
          </err:Location>
        </err:Error>
      </axsl:otherwise>
    </axsl:choose>
    <axsl:apply-templates mode="M15" select="@*|*|comment()|processing-instruction()"/>
  </axsl:template>
  <axsl:template match="text()" mode="M15" priority="-1"/>
  <axsl:template match="@*|node()" mode="M15" priority="-2">
    <axsl:apply-templates mode="M15" select="@*|node()"/>
  </axsl:template>

<!--PATTERN p49-->


	<!--RULE -->
<axsl:template match="/hd:GovTalkMessage/hd:Body/eps:IRenvelope/eps:EmployerPaymentSummary/eps:RecoverableAmountsYTD" mode="M16" priority="4000">

		<!--ASSERT -->
<axsl:choose>
      <axsl:when test="eps:SMPRecovered or            eps:SPPRecovered or            eps:SAPRecovered or            eps:ShPPRecovered or            eps:SPBPRecovered or            eps:SPBPRecoveredInNorthernIreland or           eps:SNCPRecovered or            eps:NICCompensationOnSMP or            eps:NICCompensationOnSPP or            eps:NICCompensationOnSAP or            eps:NICCompensationOnShPP or            eps:NICCompensationOnSPBP or           eps:NICCompensationOnSPBPinNorthernIreland or            eps:NICCompensationOnSNCP or            eps:CISDeductionsSuffered"/>
      <axsl:otherwise>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="errorCode">7912</axsl:variable>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="defaultMessage">There must be an entry in at least one of [SMPRECOVERED], [SPPRECOVERED], [SAPRECOVERED], [SHPPRECOVERED], [SPBPRECOVERED], [SPBPRECOVEREDNIRE], [SNCPRECOVERED], [NICCOMPENSATIONONSMP], [NICCOMPENSATIONONSPP], [NICCOMPENSATIONONSAP], [NICCOMPENSATIONONSHPP], [NICCOMPENSATIONONSPBP], [NICCOMPENSATIONONSPBPNIRE], [NICCOMPENSATIONONSNCP] or [CISDEDUCTIONSSUFFERED] if [RECOVERABLEAMOUNTSYEARTODATE] is present. Please check.</axsl:variable>
        <err:Error xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" xmlns:dsl="http://decisionsoft.com/rim/errorExtension">
          <err:RaisedBy>ChRIS</err:RaisedBy>
          <err:Number>
            <axsl:value-of select="normalize-space($errorCode)"/>
          </err:Number>
          <err:Type>business</err:Type>
          <err:Text>
            <axsl:choose>
              <axsl:when test="normalize-space($defaultMessage)">
                <axsl:copy-of select="$defaultMessage"/>
              </axsl:when>
              <axsl:otherwise>If [RECOVERABLEAMOUNTSYEARTODATE] is present, at least one of [SMPRECOVERED] or [SPPRECOVERED] or [SAPRECOVERED] or [SHPPRECOVERED] or [SPBPRECOVERED] or [SPBPRECOVEREDNIRE] or [SNCPRECOVERED] or [NICCOMPENSATIONONSMP] or [NICCOMPENSATIONONSPP] or [NICCOMPENSATIONONSAP] or [NICCOMPENSATIONONSHPP] or [NICCOMPENSATIONONSPBP] or [NICCOMPENSATIONONSPBPNIRE] or [NICCOMPENSATIONONSNCP] or [CISDEDUCTIONSSUFFERED] must be present.</axsl:otherwise>
            </axsl:choose>
          </err:Text>
          <err:Location>
            <axsl:apply-templates mode="schematron-get-full-path" select="."/>
          </err:Location>
        </err:Error>
      </axsl:otherwise>
    </axsl:choose>
    <axsl:apply-templates mode="M16" select="@*|*|comment()|processing-instruction()"/>
  </axsl:template>
  <axsl:template match="text()" mode="M16" priority="-1"/>
  <axsl:template match="@*|node()" mode="M16" priority="-2">
    <axsl:apply-templates mode="M16" select="@*|node()"/>
  </axsl:template>

<!--PATTERN p52-->


	<!--RULE -->
<axsl:template match="/hd:GovTalkMessage/hd:Body/eps:IRenvelope/eps:EmployerPaymentSummary/eps:RelatedTaxYear" mode="M17" priority="4000">

		<!--ASSERT -->
<axsl:choose>
      <axsl:when test="substring(string(2027 - 1), 3, 2) = substring(., 1, 2)           and             substring(2027, 3, 2) = substring(., 4, 2)"/>
      <axsl:otherwise>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="errorCode">7889</axsl:variable>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="defaultMessage">The Related tax year entered is invalid. Please check</axsl:variable>
        <err:Error xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" xmlns:dsl="http://decisionsoft.com/rim/errorExtension">
          <err:RaisedBy>ChRIS</err:RaisedBy>
          <err:Number>
            <axsl:value-of select="normalize-space($errorCode)"/>
          </err:Number>
          <err:Type>business</err:Type>
          <err:Text>
            <axsl:choose>
              <axsl:when test="normalize-space($defaultMessage)">
                <axsl:copy-of select="$defaultMessage"/>
              </axsl:when>
              <axsl:otherwise>Must be the appropriate tax year for the schema year. I.E. 26-27 for RTI-2027</axsl:otherwise>
            </axsl:choose>
          </err:Text>
          <err:Location>
            <axsl:apply-templates mode="schematron-get-full-path" select="."/>
          </err:Location>
        </err:Error>
      </axsl:otherwise>
    </axsl:choose>

		<!--ASSERT -->
<axsl:choose>
      <axsl:when test="(round(date:seconds(normalize-space(concat(2000 + number(substring(.,1,2)), '-04-06'))) div 86400) &lt;= round(date:seconds(normalize-space(../../eps:IRheader/eps:PeriodEnd)) div 86400))         and           (round(date:seconds(normalize-space(../../eps:IRheader/eps:PeriodEnd)) div 86400) &lt;= round(date:seconds(normalize-space(concat(2001 + number(substring(.,1,2)), '-04-05'))) div 86400))"/>
      <axsl:otherwise>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="errorCode">7844</axsl:variable>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="defaultMessage">The PeriodEnd within the IRheader must be within the same tax year as [RELATEDTAXYEAR].</axsl:variable>
        <err:Error xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" xmlns:dsl="http://decisionsoft.com/rim/errorExtension">
          <err:RaisedBy>ChRIS</err:RaisedBy>
          <err:Number>
            <axsl:value-of select="normalize-space($errorCode)"/>
          </err:Number>
          <err:Type>business</err:Type>
          <err:Text>
            <axsl:choose>
              <axsl:when test="normalize-space($defaultMessage)">
                <axsl:copy-of select="$defaultMessage"/>
              </axsl:when>
              <axsl:otherwise>The PeriodEnd within the IRheader must be within the same tax year as [RELATEDTAXYEAR].</axsl:otherwise>
            </axsl:choose>
          </err:Text>
          <err:Location>
            <axsl:apply-templates mode="schematron-get-full-path" select="."/>
          </err:Location>
        </err:Error>
      </axsl:otherwise>
    </axsl:choose>
    <axsl:apply-templates mode="M17" select="@*|*|comment()|processing-instruction()"/>
  </axsl:template>
  <axsl:template match="text()" mode="M17" priority="-1"/>
  <axsl:template match="@*|node()" mode="M17" priority="-2">
    <axsl:apply-templates mode="M17" select="@*|node()"/>
  </axsl:template>

<!--PATTERN p54-->


	<!--RULE -->
<axsl:template match="/hd:GovTalkMessage/hd:Body/eps:IRenvelope/eps:EmployerPaymentSummary/eps:FinalSubmission/eps:BecauseSchemeCeased" mode="M18" priority="4000">

		<!--ASSERT -->
<axsl:choose>
      <axsl:when test="../eps:DateSchemeCeased"/>
      <axsl:otherwise>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="errorCode">7875</axsl:variable>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="defaultMessage">[DATESCHEMECEASED] must be completed if [FINALSUBMISSIONCEASEDINDICATOR] is present</axsl:variable>
        <err:Error xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" xmlns:dsl="http://decisionsoft.com/rim/errorExtension">
          <err:RaisedBy>ChRIS</err:RaisedBy>
          <err:Number>
            <axsl:value-of select="normalize-space($errorCode)"/>
          </err:Number>
          <err:Type>business</err:Type>
          <err:Text>
            <axsl:choose>
              <axsl:when test="normalize-space($defaultMessage)">
                <axsl:copy-of select="$defaultMessage"/>
              </axsl:when>
              <axsl:otherwise>[DATESCHEMECEASED] should be present if [FINALSUBMISSIONCEASEDINDICATOR] is present</axsl:otherwise>
            </axsl:choose>
          </err:Text>
          <err:Location>
            <axsl:apply-templates mode="schematron-get-full-path" select="."/>
          </err:Location>
        </err:Error>
      </axsl:otherwise>
    </axsl:choose>
    <axsl:apply-templates mode="M18" select="@*|*|comment()|processing-instruction()"/>
  </axsl:template>
  <axsl:template match="text()" mode="M18" priority="-1"/>
  <axsl:template match="@*|node()" mode="M18" priority="-2">
    <axsl:apply-templates mode="M18" select="@*|node()"/>
  </axsl:template>

<!--PATTERN p55-->


	<!--RULE -->
<axsl:template match="/hd:GovTalkMessage/hd:Body/eps:IRenvelope/eps:EmployerPaymentSummary/eps:FinalSubmission/eps:DateSchemeCeased" mode="M19" priority="4000">

		<!--ASSERT -->
<axsl:choose>
      <axsl:when test="(round(date:seconds(normalize-space(.)) div 86400) &lt;= round(date:seconds(normalize-space(date:date())) div 86400))"/>
      <axsl:otherwise>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="errorCode">7876</axsl:variable>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="defaultMessage">The [DATESCHEMECEASED] must be today or earlier. Please check</axsl:variable>
        <err:Error xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" xmlns:dsl="http://decisionsoft.com/rim/errorExtension">
          <err:RaisedBy>ChRIS</err:RaisedBy>
          <err:Number>
            <axsl:value-of select="normalize-space($errorCode)"/>
          </err:Number>
          <err:Type>business</err:Type>
          <err:Text>
            <axsl:choose>
              <axsl:when test="normalize-space($defaultMessage)">
                <axsl:copy-of select="$defaultMessage"/>
              </axsl:when>
              <axsl:otherwise>[DATESCHEMECEASED] must not be in the future</axsl:otherwise>
            </axsl:choose>
          </err:Text>
          <err:Location>
            <axsl:apply-templates mode="schematron-get-full-path" select="."/>
          </err:Location>
        </err:Error>
      </axsl:otherwise>
    </axsl:choose>
    <axsl:apply-templates mode="M19" select="@*|*|comment()|processing-instruction()"/>
  </axsl:template>
  <axsl:template match="text()" mode="M19" priority="-1"/>
  <axsl:template match="@*|node()" mode="M19" priority="-2">
    <axsl:apply-templates mode="M19" select="@*|node()"/>
  </axsl:template>

<!--PATTERN p53-->


	<!--RULE -->
<axsl:template match="/hd:GovTalkMessage/hd:Body/eps:IRenvelope/eps:EmployerPaymentSummary/eps:FinalSubmission" mode="M20" priority="4000">

		<!--ASSERT -->
<axsl:choose>
      <axsl:when test="not ( (.) )           or             eps:BecauseSchemeCeased           or             eps:DateSchemeCeased           or             eps:ForYear"/>
      <axsl:otherwise>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="errorCode">7933</axsl:variable>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="defaultMessage">If [FINALSUBMISSION] is present then an entry in [FINALSUBMISSIONCEASEDINDICATOR], [DATESCHEMECEASED] or [FINALSUBMISSIONFORYEARINDICATOR] should be present. Please check.</axsl:variable>
        <err:Error xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" xmlns:dsl="http://decisionsoft.com/rim/errorExtension">
          <err:RaisedBy>ChRIS</err:RaisedBy>
          <err:Number>
            <axsl:value-of select="normalize-space($errorCode)"/>
          </err:Number>
          <err:Type>business</err:Type>
          <err:Text>
            <axsl:choose>
              <axsl:when test="normalize-space($defaultMessage)">
                <axsl:copy-of select="$defaultMessage"/>
              </axsl:when>
              <axsl:otherwise>If [FINALSUBMISSION] is present then [FINALSUBMISSIONCEASEDINDICATOR], [DATESCHEMECEASED] or [FINALSUBMISSIONFORYEARINDICATOR] should be present</axsl:otherwise>
            </axsl:choose>
          </err:Text>
          <err:Location>
            <axsl:apply-templates mode="schematron-get-full-path" select="."/>
          </err:Location>
        </err:Error>
      </axsl:otherwise>
    </axsl:choose>
    <axsl:apply-templates mode="M20" select="@*|*|comment()|processing-instruction()"/>
  </axsl:template>
  <axsl:template match="text()" mode="M20" priority="-1"/>
  <axsl:template match="@*|node()" mode="M20" priority="-2">
    <axsl:apply-templates mode="M20" select="@*|node()"/>
  </axsl:template>

<!--PATTERN p40-->


	<!--RULE -->
<axsl:template match="/hd:GovTalkMessage/hd:Body/eps:IRenvelope/eps:EmployerPaymentSummary" mode="M21" priority="4000">

		<!--ASSERT -->
<axsl:choose>
      <axsl:when test="../../../hd:Header/hd:MessageDetails/hd:Class = 'HMRC-PAYE-RTI-EPS'           or           ../../../hd:Header/hd:MessageDetails/hd:Class = 'HMRC-PAYE-RTI-EPS-TIL'"/>
      <axsl:otherwise>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="errorCode">7838</axsl:variable>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="defaultMessage">Valid message classes for an Employer Payment Summary are HMRC-PAYE-RTI-EPS and HMRC-PAYE-RTI-EPS-TIL.</axsl:variable>
        <err:Error xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" xmlns:dsl="http://decisionsoft.com/rim/errorExtension">
          <err:RaisedBy>ChRIS</err:RaisedBy>
          <err:Number>
            <axsl:value-of select="normalize-space($errorCode)"/>
          </err:Number>
          <err:Type>business</err:Type>
          <err:Text>
            <axsl:choose>
              <axsl:when test="normalize-space($defaultMessage)">
                <axsl:copy-of select="$defaultMessage"/>
              </axsl:when>
              <axsl:otherwise>Valid message classes for an Employer Payment Summary are HMRC-PAYE-RTI-EPS and HMRC-PAYE-RTI-EPS-TIL.</axsl:otherwise>
            </axsl:choose>
          </err:Text>
          <err:Location>
            <axsl:apply-templates mode="schematron-get-full-path" select="."/>
          </err:Location>
        </err:Error>
      </axsl:otherwise>
    </axsl:choose>

		<!--ASSERT -->
<axsl:choose>
      <axsl:when test="eps:NoPaymentForPeriod or eps:PeriodOfInactivity or eps:EmpAllceInd or eps:RecoverableAmountsYTD or eps:ApprenticeshipLevy or eps:Account or eps:FinalSubmission"/>
      <axsl:otherwise>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="errorCode">7913</axsl:variable>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="defaultMessage">On an Employer Payment Submission there must be an entry in at least one of [NOPAYMENTFORPERIOD], [PERIODOFINACTIVITY], [EMPLOYMENTALLOWANCEINDICATOR], [RECOVERABLEAMOUNTSYEARTODATE], [APPRENTICESHIPLEVY], [ACCOUNTINFORMATION] or [FINALSUBMISSION]. Please check.</axsl:variable>
        <err:Error xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" xmlns:dsl="http://decisionsoft.com/rim/errorExtension">
          <err:RaisedBy>ChRIS</err:RaisedBy>
          <err:Number>
            <axsl:value-of select="normalize-space($errorCode)"/>
          </err:Number>
          <err:Type>business</err:Type>
          <err:Text>
            <axsl:choose>
              <axsl:when test="normalize-space($defaultMessage)">
                <axsl:copy-of select="$defaultMessage"/>
              </axsl:when>
              <axsl:otherwise>At least one of [NOPAYMENTFORPERIOD], [PERIODOFINACTIVITY], [EMPLOYMENTALLOWANCEINDICATOR], [RECOVERABLEAMOUNTSYEARTODATE], [APPRENTICESHIPLEVY], [ACCOUNTINFORMATION] or [FINALSUBMISSION] must be submitted.</axsl:otherwise>
            </axsl:choose>
          </err:Text>
          <err:Location>
            <axsl:apply-templates mode="schematron-get-full-path" select="."/>
          </err:Location>
        </err:Error>
      </axsl:otherwise>
    </axsl:choose>
    <axsl:apply-templates mode="M21" select="@*|*|comment()|processing-instruction()"/>
  </axsl:template>
  <axsl:template match="text()" mode="M21" priority="-1"/>
  <axsl:template match="@*|node()" mode="M21" priority="-2">
    <axsl:apply-templates mode="M21" select="@*|node()"/>
  </axsl:template>
</axsl:stylesheet>
